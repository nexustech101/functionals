from __future__ import annotations

import json
from pathlib import Path

import pytest

import functionals.cron as cron
from functionals.cron import CronRegistry
from functionals.cron.runtime import CronRuntimeEngine
from functionals.cron.state import (
    clear_state_caches,
    create_event,
    cron_event_registry,
    cron_run_registry,
    mark_event,
)


@pytest.fixture(autouse=True)
def _reset_cron_state() -> None:
    cron.reset_registry()
    clear_state_caches()
    yield
    cron.reset_registry()
    clear_state_caches()


@pytest.mark.asyncio
async def test_module_level_retry_fixed_succeeds_on_second_attempt(tmp_path: Path) -> None:
    calls = {"count": 0}
    seen_payloads: list[dict[str, object]] = []

    @cron.job(
        name="deploy-module",
        trigger=cron.event("manual"),
        retry_policy="fixed",
        retry_max_attempts=3,
        retry_backoff_seconds=0.0,
    )
    def deploy_module(payload: dict[str, object] | None = None) -> str:
        seen_payloads.append(dict(payload or {}))
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("first attempt failed")
        return "ok"

    engine = CronRuntimeEngine(root=tmp_path, registry=cron.get_registry())

    event = create_event(
        root=tmp_path,
        job_name="deploy-module",
        source="manual",
        payload={"env": "prod"},
        status="queued",
    )
    await engine._execute_event(event)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert len(rows) == 2
    assert rows[0].status == "failed"
    assert rows[1].source == "retry"
    assert rows[1].status == "pending"
    pending_payload = json.loads(rows[1].payload)
    assert pending_payload["env"] == "prod"
    assert pending_payload["__fx_retry"]["attempt"] == 2

    queued_retry = mark_event(rows[1], status="queued")
    await engine._execute_event(queued_retry)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert rows[1].status == "processed"

    runs = cron_run_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert len(runs) == 2
    assert runs[0].status == "failure"
    assert runs[1].status == "success"
    assert seen_payloads == [{"env": "prod"}, {"env": "prod"}]


@pytest.mark.asyncio
async def test_module_level_retry_dead_letters_after_max_attempts(tmp_path: Path) -> None:
    @cron.job(
        name="deploy-dead-letter",
        trigger=cron.event("manual"),
        retry_policy="fixed",
        retry_max_attempts=2,
        retry_backoff_seconds=0.0,
    )
    def deploy_dead_letter(payload: dict[str, object] | None = None) -> str:
        _ = payload
        raise RuntimeError("always fails")

    engine = CronRuntimeEngine(root=tmp_path, registry=cron.get_registry())

    event = create_event(
        root=tmp_path,
        job_name="deploy-dead-letter",
        source="manual",
        payload={"env": "prod"},
        status="queued",
    )
    await engine._execute_event(event)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert len(rows) == 2
    assert rows[0].status == "failed"
    assert rows[1].status == "pending"

    queued_retry = mark_event(rows[1], status="queued")
    await engine._execute_event(queued_retry)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert rows[1].status == "dead_letter"
    assert "dead-lettered" in rows[1].error

    pending = cron_event_registry(tmp_path).filter(
        project_root=str(tmp_path),
        status="pending",
        order_by="id",
    )
    assert pending == []

    runs = cron_run_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert len(runs) == 2
    assert runs[0].status == "failure"
    assert runs[1].status == "failure"


@pytest.mark.asyncio
async def test_instance_retry_exponential_uses_backoff_and_jitter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = CronRegistry()

    @registry.job(
        name="deploy-instance",
        trigger=registry.event("manual"),
        retry_policy="exponential",
        retry_max_attempts=3,
        retry_backoff_seconds=10.0,
        retry_max_backoff_seconds=30.0,
        retry_jitter_seconds=2.0,
    )
    def deploy_instance(payload: dict[str, object] | None = None) -> str:
        _ = payload
        raise RuntimeError("boom")

    engine = CronRuntimeEngine(root=tmp_path, registry=registry)

    monkeypatch.setattr("functionals.cron.runtime.random.uniform", lambda _a, _b: 1.5)
    monkeypatch.setattr("functionals.cron.runtime.time.time", lambda: 1000.0)

    event = create_event(
        root=tmp_path,
        job_name="deploy-instance",
        source="manual",
        payload={"env": "stage"},
        status="queued",
    )
    await engine._execute_event(event)

    rows = cron_event_registry(tmp_path).filter(project_root=str(tmp_path), order_by="id")
    assert len(rows) == 2
    retry_payload = json.loads(rows[1].payload)
    retry_meta = retry_payload["__fx_retry"]
    assert retry_meta["attempt"] == 2
    assert retry_meta["max_attempts"] == 3
    assert retry_meta["not_before_epoch"] == pytest.approx(1011.5)

    monkeypatch.setattr("functionals.cron.runtime.time.time", lambda: 1010.0)
    assert engine._retry_event_ready(retry_payload) is False

    monkeypatch.setattr("functionals.cron.runtime.time.time", lambda: 1012.0)
    assert engine._retry_event_ready(retry_payload) is True


def test_retry_policy_validation_for_module_and_instance_modes() -> None:
    with pytest.raises(ValueError, match="retry_policy must be one of"):
        @cron.job(name="bad-module", trigger=cron.event("manual"), retry_policy="invalid")
        def _bad_module() -> None:
            return None

    registry = CronRegistry()
    with pytest.raises(ValueError, match="retry_backoff_seconds must be >= 0"):
        @registry.job(
            name="bad-instance",
            trigger=registry.event("manual"),
            retry_policy="fixed",
            retry_backoff_seconds=-1.0,
        )
        def _bad_instance() -> None:
            return None

