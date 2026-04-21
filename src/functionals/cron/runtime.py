"""
Async runtime for executing registered cron jobs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import inspect
import json
from pathlib import Path
import random
import signal
import time
from typing import Any

from functionals.cron.decorators import get_registry
from functionals.cron.discovery import load_project_jobs
from functionals.cron.registry import CronRegistry
from functionals.cron.state import (
    CronEventRecord,
    create_event,
    cron_event_registry,
    heartbeat_runtime,
    mark_event,
    mark_runtime_stopped,
    parse_json,
    record_run,
    resolve_root,
    sync_registry_to_state,
    utc_now,
    upsert_runtime,
)


@dataclass(frozen=True)
class RuntimeSummary:
    root: str
    jobs: int
    workers: int
    webhook_enabled: bool


@dataclass(frozen=True)
class RetryConfig:
    policy: str
    max_attempts: int
    backoff_seconds: float
    max_backoff_seconds: float
    jitter_seconds: float


_RETRY_META_KEY = "__fx_retry"


def sync_project_jobs(
    root: str | Path = ".",
    *,
    registry: CronRegistry | None = None,
) -> tuple[str | None, int, int]:
    root_path = resolve_root(root)
    active_registry = get_registry() if registry is None else registry
    package, loaded_modules = load_project_jobs(
        root_path,
        clear_registry=True,
        registry=active_registry,
    )
    entries = list(active_registry.all().values())
    sync_registry_to_state(root_path, entries)
    return package, loaded_modules, len(entries)


def _cron_piece_matches(field: str, value: int) -> bool:
    part = field.strip()
    if part == "*":
        return True
    if part.startswith("*/"):
        try:
            step = int(part[2:])
        except ValueError:
            return False
        return step > 0 and value % step == 0
    for token in part.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit() and int(token) == value:
            return True
    return False


def cron_matches(expression: str, now: datetime) -> bool:
    fields = expression.split()
    if len(fields) != 5:
        return False
    minute, hour, dom, mon, dow = fields
    cron_dow = (now.weekday() + 1) % 7
    return (
        _cron_piece_matches(minute, now.minute)
        and _cron_piece_matches(hour, now.hour)
        and _cron_piece_matches(dom, now.day)
        and _cron_piece_matches(mon, now.month)
        and (_cron_piece_matches(dow, cron_dow) or (dow == "7" and cron_dow == 0))
    )


class CronRuntimeEngine:
    def __init__(
        self,
        *,
        root: str | Path = ".",
        workers: int = 4,
        poll_interval: float = 1.0,
        webhook_host: str = "127.0.0.1",
        webhook_port: int = 8787,
        registry: CronRegistry | None = None,
    ) -> None:
        self.root = resolve_root(root)
        self.workers = max(1, int(workers))
        self.poll_interval = max(0.2, float(poll_interval))
        self.webhook_host = webhook_host
        self.webhook_port = int(webhook_port)
        self._registry = get_registry() if registry is None else registry

        self._queue: asyncio.Queue[CronEventRecord] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._running_jobs: set[str] = set()
        self._interval_next: dict[str, float] = {}
        self._cron_last_key: dict[str, str] = {}
        self._file_last_mtime: dict[str, float] = {}
        self._file_last_emit: dict[str, float] = {}
        self._server: asyncio.AbstractServer | None = None

    def _jobs(self) -> dict[str, Any]:
        return self._registry.all()

    @staticmethod
    def _retry_config(entry: Any) -> RetryConfig:
        return RetryConfig(
            policy=str(getattr(entry, "retry_policy", "none") or "none").strip().lower(),
            max_attempts=max(0, int(getattr(entry, "retry_max_attempts", 0) or 0)),
            backoff_seconds=max(0.0, float(getattr(entry, "retry_backoff_seconds", 0.0) or 0.0)),
            max_backoff_seconds=max(0.0, float(getattr(entry, "retry_max_backoff_seconds", 0.0) or 0.0)),
            jitter_seconds=max(0.0, float(getattr(entry, "retry_jitter_seconds", 0.0) or 0.0)),
        )

    @staticmethod
    def _strip_retry_meta(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            if payload is None:
                return {}
            return {"value": payload}
        clean = dict(payload)
        clean.pop(_RETRY_META_KEY, None)
        return clean

    @staticmethod
    def _retry_attempt(payload: Any) -> int:
        if not isinstance(payload, dict):
            return 1
        raw = payload.get(_RETRY_META_KEY, {})
        if not isinstance(raw, dict):
            return 1
        try:
            attempt = int(raw.get("attempt", 1))
        except (TypeError, ValueError):
            return 1
        return max(1, attempt)

    @staticmethod
    def _retry_event_ready(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return True
        raw = payload.get(_RETRY_META_KEY, {})
        if not isinstance(raw, dict):
            return True
        try:
            not_before = float(raw.get("not_before_epoch", 0.0))
        except (TypeError, ValueError):
            return True
        return time.time() >= max(0.0, not_before)

    @staticmethod
    def _retry_delay(config: RetryConfig, attempt: int) -> float:
        if config.policy == "none" or config.max_attempts <= 0:
            return 0.0
        if config.policy == "fixed":
            delay = config.backoff_seconds
        else:
            delay = config.backoff_seconds * (2 ** max(0, attempt - 1))
        if config.max_backoff_seconds > 0:
            delay = min(delay, config.max_backoff_seconds)
        if config.jitter_seconds > 0:
            delay += random.uniform(0.0, config.jitter_seconds)
        return max(0.0, delay)

    @staticmethod
    def _build_retry_payload(
        payload: dict[str, Any],
        *,
        attempt: int,
        max_attempts: int,
        not_before_epoch: float,
    ) -> dict[str, Any]:
        next_payload = dict(payload)
        next_payload[_RETRY_META_KEY] = {
            "attempt": max(1, int(attempt)),
            "max_attempts": max(1, int(max_attempts)),
            "not_before_epoch": max(0.0, float(not_before_epoch)),
        }
        return next_payload

    async def run_forever(self) -> RuntimeSummary:
        sync_project_jobs(self.root, registry=self._registry)
        jobs = self._jobs()
        upsert_runtime(
            root=self.root,
            pid=self._pid(),
            status="running",
            workers=self.workers,
        )

        loop = asyncio.get_running_loop()
        self._attach_signal_handlers(loop)

        worker_tasks = [asyncio.create_task(self._worker_loop()) for _ in range(self.workers)]
        tasks = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._schedule_loop()),
            asyncio.create_task(self._manual_event_loop()),
            asyncio.create_task(self._file_change_loop()),
        ]

        webhook_enabled = any(
            entry.trigger.kind == "webhook" and entry.enabled for entry in jobs.values()
        )
        if webhook_enabled:
            self._server = await asyncio.start_server(
                self._handle_webhook_client,
                host=self.webhook_host,
                port=self.webhook_port,
            )

        try:
            await self._stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            for task in worker_tasks:
                task.cancel()
            await asyncio.gather(*tasks, *worker_tasks, return_exceptions=True)

            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
            mark_runtime_stopped(self.root)

        return RuntimeSummary(
            root=str(self.root),
            jobs=len(jobs),
            workers=self.workers,
            webhook_enabled=webhook_enabled,
        )

    def stop(self) -> None:
        self._stop.set()

    def _attach_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except Exception:
                # Windows event loops may not support add_signal_handler.
                pass

    @staticmethod
    def _pid() -> int:
        import os
        return os.getpid()

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            heartbeat_runtime(self.root)
            await asyncio.sleep(5.0)

    async def _schedule_loop(self) -> None:
        while not self._stop.is_set():
            jobs = self._jobs()
            now_dt = datetime.now()
            now_ts = time.time()
            minute_key = now_dt.strftime("%Y%m%d%H%M")

            for name, entry in jobs.items():
                if not entry.enabled:
                    continue
                if entry.trigger.kind == "interval":
                    seconds = int(entry.trigger.config.get("seconds", 0))
                    if seconds <= 0:
                        continue
                    next_at = self._interval_next.get(name, now_ts + seconds)
                    if now_ts >= next_at:
                        self._interval_next[name] = now_ts + seconds
                        await self._enqueue_job(name, source="interval", payload={"seconds": seconds})
                elif entry.trigger.kind == "cron":
                    expression = str(entry.trigger.config.get("expression", "")).strip()
                    if not expression:
                        continue
                    if self._cron_last_key.get(name) == minute_key:
                        continue
                    if cron_matches(expression, now_dt):
                        self._cron_last_key[name] = minute_key
                        await self._enqueue_job(name, source="cron", payload={"expression": expression})
            await asyncio.sleep(self.poll_interval)

    async def _manual_event_loop(self) -> None:
        while not self._stop.is_set():
            pending = cron_event_registry(self.root).filter(
                project_root=str(self.root),
                status="pending",
                order_by="id",
                limit=100,
            )
            for item in pending:
                payload = parse_json(item.payload, {})
                if not self._retry_event_ready(payload):
                    continue
                queued = mark_event(item, status="queued")
                await self._queue.put(queued)
            await asyncio.sleep(self.poll_interval)

    async def _file_change_loop(self) -> None:
        while not self._stop.is_set():
            jobs = self._jobs()
            now_ts = time.time()
            for name, entry in jobs.items():
                if not entry.enabled or entry.trigger.kind != "file_change":
                    continue
                trigger = entry.trigger.config
                paths = trigger.get("paths", [])
                if not isinstance(paths, list):
                    continue
                debounce = float(trigger.get("debounce_seconds", 2.0))
                latest = self._latest_mtime(paths)
                if latest <= 0:
                    continue
                prev = self._file_last_mtime.get(name, 0.0)
                if latest > prev:
                    last_emit = self._file_last_emit.get(name, 0.0)
                    if now_ts - last_emit >= debounce:
                        self._file_last_mtime[name] = latest
                        self._file_last_emit[name] = now_ts
                        await self._enqueue_job(
                            name,
                            source="file_change",
                            payload={"paths": paths, "mtime": latest},
                        )
            await asyncio.sleep(self.poll_interval)

    def _latest_mtime(self, patterns: list[str]) -> float:
        latest = 0.0
        for raw in patterns:
            pattern = str(raw).strip()
            if not pattern:
                continue
            path = Path(pattern)
            if not path.is_absolute():
                path = self.root / pattern

            if any(ch in pattern for ch in ["*", "?", "[", "]"]):
                for match in self.root.glob(pattern):
                    try:
                        latest = max(latest, match.stat().st_mtime)
                    except OSError:
                        continue
                continue

            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
        return latest

    async def _handle_webhook_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        body = await reader.read(65536)
        text = body.decode("utf-8", errors="ignore")
        lines = text.split("\r\n")
        if not lines:
            await self._write_http(writer, 400, "bad request")
            return
        req = lines[0].split()
        if len(req) < 2:
            await self._write_http(writer, 400, "bad request")
            return

        method = req[0].upper()
        path = req[1].split("?")[0]
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        if method not in {"POST", "PUT"}:
            await self._write_http(writer, 405, "method not allowed")
            return

        matched = 0
        token = headers.get("x-functionals-token", "")
        for entry in self._jobs().values():
            if not entry.enabled or entry.trigger.kind != "webhook":
                continue
            config = entry.trigger.config
            if str(config.get("path", "")).strip() != path:
                continue
            expected = str(config.get("token", "")).strip()
            if expected and expected != token:
                continue
            await self._enqueue_job(
                entry.name,
                source="webhook",
                payload={"path": path},
            )
            matched += 1

        if matched == 0:
            await self._write_http(writer, 404, "not found")
            return
        await self._write_http(writer, 202, "accepted")

    async def _write_http(self, writer: asyncio.StreamWriter, status: int, message: str) -> None:
        payload = message.encode("utf-8")
        reason = {
            200: "OK",
            202: "Accepted",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
        }.get(status, "OK")
        response = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8") + payload
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _enqueue_job(self, job_name: str, *, source: str, payload: dict[str, Any]) -> None:
        event = create_event(
            root=self.root,
            job_name=job_name,
            source=source,
            payload=payload,
            status="queued",
        )
        await self._queue.put(event)

    async def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue

            try:
                await self._execute_event(event)
            finally:
                self._queue.task_done()

    async def _execute_event(self, event: CronEventRecord) -> None:
        jobs = self._jobs()
        entry = jobs.get(event.job_name)
        if entry is None:
            mark_event(event, status="failed", error=f"Unknown job '{event.job_name}'.")
            return
        if not entry.enabled:
            mark_event(event, status="skipped")
            return
        if entry.name in self._running_jobs and entry.overlap_policy == "skip":
            started = utc_now()
            finished = utc_now()
            mark_event(event, status="skipped")
            record_run(
                root=self.root,
                job_name=entry.name,
                event_id=event.id,
                status="skipped",
                message="Skipped due to overlap policy.",
                started_at=started,
                finished_at=finished,
                duration_ms=0,
            )
            return

        self._running_jobs.add(entry.name)
        started_at = utc_now()
        begin = time.perf_counter()
        raw_payload = parse_json(event.payload, {})
        payload = self._strip_retry_meta(raw_payload)
        attempt = self._retry_attempt(raw_payload)
        retry = self._retry_config(entry)

        try:
            kwargs = {}
            sig = inspect.signature(entry.handler)
            if "event" in sig.parameters:
                kwargs["event"] = {
                    "id": event.id,
                    "source": event.source,
                    "payload": payload,
                }
            if "payload" in sig.parameters and "payload" not in kwargs:
                kwargs["payload"] = payload

            if inspect.iscoroutinefunction(entry.handler):
                task = entry.handler(**kwargs)
            else:
                task = asyncio.to_thread(entry.handler, **kwargs)

            if entry.max_runtime > 0:
                result = await asyncio.wait_for(task, timeout=entry.max_runtime)
            else:
                result = await task

            duration = int((time.perf_counter() - begin) * 1000)
            mark_event(event, status="processed")
            record_run(
                root=self.root,
                job_name=entry.name,
                event_id=event.id,
                status="success",
                message="" if result is None else str(result),
                started_at=started_at,
                finished_at=utc_now(),
                duration_ms=duration,
            )
        except TimeoutError:
            duration = int((time.perf_counter() - begin) * 1000)
            await self._handle_execution_failure(
                event=event,
                entry=entry,
                payload=payload,
                attempt=attempt,
                retry=retry,
                started_at=started_at,
                duration_ms=duration,
                error_message="Job execution timed out.",
            )
        except Exception as exc:
            duration = int((time.perf_counter() - begin) * 1000)
            await self._handle_execution_failure(
                event=event,
                entry=entry,
                payload=payload,
                attempt=attempt,
                retry=retry,
                started_at=started_at,
                duration_ms=duration,
                error_message=str(exc),
            )
        finally:
            self._running_jobs.discard(entry.name)

    async def _handle_execution_failure(
        self,
        *,
        event: CronEventRecord,
        entry: Any,
        payload: dict[str, Any],
        attempt: int,
        retry: RetryConfig,
        started_at: str,
        duration_ms: int,
        error_message: str,
    ) -> None:
        can_retry = (
            retry.policy != "none"
            and retry.max_attempts > 0
            and attempt < retry.max_attempts
        )
        if can_retry:
            next_attempt = attempt + 1
            delay = self._retry_delay(retry, attempt)
            retry_event = create_event(
                root=self.root,
                job_name=entry.name,
                source="retry",
                payload=self._build_retry_payload(
                    payload,
                    attempt=next_attempt,
                    max_attempts=retry.max_attempts,
                    not_before_epoch=time.time() + delay,
                ),
                status="pending",
            )
            reason = (
                f"{error_message} (retry {next_attempt}/{retry.max_attempts} "
                f"scheduled in {delay:.2f}s as event {retry_event.id})"
            )
            mark_event(event, status="failed", error=reason)
            record_run(
                root=self.root,
                job_name=entry.name,
                event_id=event.id,
                status="failure",
                message=reason,
                started_at=started_at,
                finished_at=utc_now(),
                duration_ms=duration_ms,
            )
            return

        final_status = "dead_letter" if retry.policy != "none" and retry.max_attempts > 0 else "failed"
        if final_status == "dead_letter":
            reason = (
                f"{error_message} (dead-lettered after attempt "
                f"{attempt}/{retry.max_attempts})"
            )
        else:
            reason = error_message

        mark_event(event, status=final_status, error=reason)
        record_run(
            root=self.root,
            job_name=entry.name,
            event_id=event.id,
            status="failure",
            message=reason,
            started_at=started_at,
            finished_at=utc_now(),
            duration_ms=duration_ms,
        )


async def run_daemon(
    *,
    root: str | Path = ".",
    workers: int = 4,
    poll_interval: float = 1.0,
    webhook_host: str = "127.0.0.1",
    webhook_port: int = 8787,
    registry: CronRegistry | None = None,
) -> RuntimeSummary:
    engine = CronRuntimeEngine(
        root=root,
        workers=workers,
        poll_interval=poll_interval,
        webhook_host=webhook_host,
        webhook_port=webhook_port,
        registry=registry,
    )
    return await engine.run_forever()


def build_event_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"value": value}
