from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import registers.cli as cli
import registers.cron as cron
from registers.cron import CronRegistry
from registers.cron.adapters import AdapterReport
from registers.cron.runtime import (
    CronRuntimeEngine,
    WatchdogEventPayload,
    WatchdogFileEventSource,
)
from registers.cron.state import (
    clear_state_caches,
    cron_event_registry,
    cron_job_registry,
    cron_run_registry,
)


@pytest.fixture(autouse=True)
def _reset_cron_state() -> None:
    cli.reset_registry()
    cron.reset_registry()
    clear_state_caches()
    yield
    cli.reset_registry()
    cron.reset_registry()
    clear_state_caches()


def test_module_level_job_supports_bare_decorator_default_manual_and_run(tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    @cron.job
    def rebuild(payload: dict[str, object] | None = None) -> str:
        seen.append(dict(payload or {}))
        return "rebuilt"

    entry = cron.get_registry().get("rebuild")
    assert entry.trigger.kind == "manual"

    result = cron.run("rebuild", payload={"dry_run": True}, root=tmp_path)

    assert result == "rebuilt"
    assert seen == [{"dry_run": True}]
    runs = cron_run_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert runs[0].status == "success"
    assert runs[0].message == "rebuilt"


def test_module_level_job_supports_empty_call_and_explicit_trigger() -> None:
    @cron.job()
    def default_job() -> None:
        return None

    @cron.job(name="calendar-job", trigger=cron.cron("0 2 * * *"))
    def calendar_job() -> None:
        return None

    entries = cron.get_registry().all()
    assert entries["default-job"].trigger.kind == "manual"
    assert entries["calendar-job"].trigger.kind == "cron"


def test_instance_registry_facade_is_isolated_and_runs_async_handlers(tmp_path: Path) -> None:
    first = CronRegistry()
    second = CronRegistry()

    @first.job
    async def sync(payload: dict[str, object] | None = None) -> str:
        await asyncio.sleep(0)
        return f"first:{payload['value']}"

    @second.job
    def sync() -> str:
        return "second"

    assert first.run("sync", payload={"value": "ok"}, root=tmp_path) == "first:ok"
    assert second.run("sync", root=tmp_path) == "second"
    assert cron.get_registry().all() == {}


def test_watch_shortcut_registers_file_change_trigger() -> None:
    registry = CronRegistry()

    @registry.watch("src/**/*.py", debounce_seconds=0.5, ignore_patterns=["src/**/__pycache__/**"])
    def rebuild() -> str:
        return "ok"

    entry = registry.get("rebuild")
    assert entry.trigger.kind == "file_change"
    assert entry.trigger.config["paths"] == ["src/**/*.py"]
    assert entry.trigger.config["debounce_seconds"] == 0.5
    assert entry.trigger.config["recursive"] is True
    assert entry.trigger.config["ignore_patterns"] == ["src/**/__pycache__/**"]


def test_durable_register_syncs_selected_job_and_uses_adapter_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_generate(**kwargs: Any) -> AdapterReport:
        calls.append(("generate", kwargs))
        return AdapterReport(created=("artifact",))

    def _fake_apply(**kwargs: Any) -> AdapterReport:
        calls.append(("apply", kwargs))
        return AdapterReport(applied=("deploy",))

    monkeypatch.setattr("registers.cron.adapters.generate_artifacts", _fake_generate)
    monkeypatch.setattr("registers.cron.adapters.apply_artifacts", _fake_apply)

    @cron.job(name="deploy", trigger=cron.event("manual"), target="github_actions")
    def deploy() -> str:
        return "ok"

    @cron.job(name="cleanup", trigger=cron.interval(minutes=5))
    def cleanup() -> str:
        return "ok"

    report = cron.register("deploy", root=tmp_path, apply=True)

    assert report.synced == ("deploy",)
    assert calls == [
        (
            "generate",
            {
                "root": tmp_path.resolve(),
                "target": "",
                "job_name": "deploy",
                "execution_command": "",
            },
        ),
        (
            "apply",
            {
                "root": tmp_path.resolve(),
                "target": "",
                "job_name": "deploy",
                "execution_command": "",
            },
        ),
    ]
    rows = cron_job_registry(tmp_path).filter(project_root=str(tmp_path), order_by="name")
    assert [row.name for row in rows] == ["deploy"]


def test_legacy_callable_register_still_adds_job() -> None:
    registry = CronRegistry()

    def legacy() -> str:
        return "ok"

    entry = registry.register(legacy, name="legacy", trigger=registry.event("manual"))

    assert entry.name == "legacy"
    assert registry.get("legacy").handler is legacy


@pytest.mark.asyncio
async def test_run_records_failure_without_raising(tmp_path: Path) -> None:
    @cron.job
    def fail() -> str:
        raise RuntimeError("boom")

    engine = CronRuntimeEngine(root=tmp_path, registry=cron.get_registry())
    event = cron_event_registry(tmp_path).create(
        project_root=str(tmp_path.resolve()),
        job_name="fail",
        source="manual",
        payload=json.dumps({}),
        status="queued",
        created_at="2026-01-01T00:00:00Z",
    )

    assert await engine._execute_event(event) is None
    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path.resolve()), order_by="id")
    runs = cron_run_registry(tmp_path).filter(project_root=str(tmp_path.resolve()), order_by="id")
    assert rows[0].status == "failed"
    assert runs[0].status == "failure"


def test_watchdog_source_schedules_expected_paths_and_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {"scheduled": [], "started": 0, "stopped": 0, "joined": 0}

    class _FakeObserver:
        def schedule(self, handler: Any, path: str, recursive: bool = False) -> object:
            calls["scheduled"].append((Path(path), recursive, handler))
            return object()

        def start(self) -> None:
            calls["started"] += 1

        def stop(self) -> None:
            calls["stopped"] += 1

        def join(self) -> None:
            calls["joined"] += 1

    monkeypatch.setattr("registers.cron.runtime.Observer", _FakeObserver)

    registry = CronRegistry()

    @registry.watch("src/**/*.py", recursive=True)
    def rebuild() -> str:
        return "ok"

    source = WatchdogFileEventSource(
        root=tmp_path,
        jobs=registry.all(),
        callback=lambda _event: None,
    )

    assert source.start() is True
    assert len(calls["scheduled"]) == 1
    assert calls["scheduled"][0][0] == tmp_path
    assert calls["scheduled"][0][1] is True
    assert calls["started"] == 1

    source.stop()
    assert calls["stopped"] == 1
    assert calls["joined"] == 1


@pytest.mark.asyncio
async def test_watchdog_events_enqueue_file_change_payload_and_debounce(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CronRegistry()

    @registry.watch("src/**/*.py", debounce_seconds=10.0)
    def rebuild(payload: dict[str, object] | None = None) -> str:
        _ = payload
        return "ok"

    engine = CronRuntimeEngine(root=tmp_path, registry=registry)
    monkeypatch.setattr("registers.cron.runtime.time.monotonic", lambda: 100.0)
    event = WatchdogEventPayload(
        path=str(tmp_path / "src" / "app.py"),
        dest_path="",
        event_type="modified",
        is_directory=False,
    )

    await engine._handle_file_event(event)
    await engine._handle_file_event(event)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path.resolve()), order_by="id")
    assert len(rows) == 1
    payload = json.loads(rows[0].payload)
    assert rows[0].source == "file_change"
    assert payload["path"] == str(tmp_path / "src" / "app.py")
    assert payload["event_type"] == "modified"
    assert payload["patterns"] == ["src/**/*.py"]
    assert payload["matched_job"] == "rebuild"


@pytest.mark.asyncio
async def test_watchdog_events_respect_ignore_patterns(tmp_path: Path) -> None:
    registry = CronRegistry()

    @registry.watch("src/**/*.py", ignore_patterns=["src/**/__pycache__/**"])
    def rebuild() -> str:
        return "ok"

    engine = CronRuntimeEngine(root=tmp_path, registry=registry)
    event = WatchdogEventPayload(
        path=str(tmp_path / "src" / "__pycache__" / "app.py"),
        dest_path="",
        event_type="created",
        is_directory=False,
    )

    await engine._handle_file_event(event)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path.resolve()), order_by="id")
    assert rows == []


def test_install_cli_manages_jobs_defined_in_script(tmp_path: Path) -> None:
    cli_registry = cli.CommandRegistry()
    cron_registry = CronRegistry()
    seen: list[dict[str, object]] = []

    @cron_registry.job
    def rebuild(payload: dict[str, object] | None = None) -> str:
        seen.append(dict(payload or {}))
        return "rebuilt"

    cron.install_cli(
        cli_registry=cli_registry,
        cron_registry=cron_registry,
        execution_command="python app.py cron run {job} {root}",
    )

    jobs = cli_registry.run(["cron", "jobs"], print_result=False)
    assert "rebuild (manual" in jobs

    result = cli_registry.run(
        ["cron", "run", "rebuild", str(tmp_path), "--payload", '{"dry_run": true}'],
        print_result=False,
    )

    assert "Cron Run Result" in result
    assert "Result: rebuilt" in result
    assert seen == [{"dry_run": True}]


def test_install_cli_register_uses_platform_target_and_script_execution_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli_registry = cli.CommandRegistry()
    cron_registry = CronRegistry()
    calls: list[tuple[str, dict[str, Any]]] = []

    def _fake_generate(**kwargs: Any) -> AdapterReport:
        calls.append(("generate", kwargs))
        return AdapterReport(created=("artifact",))

    def _fake_apply(**kwargs: Any) -> AdapterReport:
        calls.append(("apply", kwargs))
        return AdapterReport(applied=("job",))

    monkeypatch.setattr("registers.cron.adapters.generate_artifacts", _fake_generate)
    monkeypatch.setattr("registers.cron.adapters.apply_artifacts", _fake_apply)

    @cron_registry.job(name="nightly", trigger=cron_registry.cron("0 2 * * *"))
    def nightly() -> str:
        return "ok"

    cron.install_cli(
        cli_registry=cli_registry,
        cron_registry=cron_registry,
        execution_command="python app.py cron run {job} {root}",
    )

    output = cli_registry.run(
        ["cron", "register", "nightly", str(tmp_path), "--apply"],
        print_result=False,
    )

    platform_target = "windows_task_scheduler" if __import__("os").name == "nt" else "linux_cron"
    assert "Cron Register Result" in output
    assert f"Target: {platform_target}" in output
    assert calls == [
        (
            "generate",
            {
                "root": tmp_path.resolve(),
                "target": platform_target,
                "job_name": "nightly",
                "execution_command": "python app.py cron run {job} {root}",
            },
        ),
        (
            "apply",
            {
                "root": tmp_path.resolve(),
                "target": platform_target,
                "job_name": "nightly",
                "execution_command": "python app.py cron run {job} {root}",
            },
        ),
    ]
