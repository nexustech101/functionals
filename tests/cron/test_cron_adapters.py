from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from registers.cron import adapters
from registers.cron.adapters import apply_artifacts, generate_artifacts
from registers.cron.state import clear_state_caches, cron_job_registry, utc_now


@pytest.fixture(autouse=True)
def _clear_state_cache() -> None:
    clear_state_caches()
    yield
    clear_state_caches()


def _upsert_job(
    root: Path,
    *,
    name: str,
    target: str,
    deployment_file: str,
    trigger_kind: str = "cron",
    trigger_config: dict[str, object] | None = None,
) -> None:
    root_path = root.resolve()
    reg = cron_job_registry(root_path)
    job_key = f"{root_path}:{name}"
    existing = reg.get(job_key=job_key)
    created_at = existing.created_at if existing is not None else utc_now()
    config = trigger_config or {"expression": "*/5 * * * *"}

    reg.upsert(
        id=getattr(existing, "id", None),
        job_key=job_key,
        project_root=str(root_path),
        name=name,
        target=target,
        trigger_kind=trigger_kind,
        trigger_config=json.dumps(config, sort_keys=True),
        deployment_file=deployment_file,
        enabled=True,
        max_runtime=0,
        tags="[]",
        overlap_policy="skip",
        retry_policy="none",
        retry_max_attempts=0,
        retry_backoff_seconds=0.0,
        retry_max_backoff_seconds=0.0,
        retry_jitter_seconds=0.0,
        handler_module="app.jobs",
        handler_qualname=name,
        created_at=created_at,
        updated_at=utc_now(),
    )


def test_generate_artifacts_create_update_and_skip(tmp_path: Path) -> None:
    artifact_path = tmp_path / "ops" / "workflows" / "cron" / "nightly.cron"
    _upsert_job(
        tmp_path,
        name="nightly",
        target="linux_cron",
        deployment_file=str(artifact_path),
    )

    first = generate_artifacts(root=tmp_path)
    assert str(artifact_path) in first.created
    assert artifact_path.exists()

    second = generate_artifacts(root=tmp_path)
    assert str(artifact_path) in second.skipped

    _upsert_job(
        tmp_path,
        name="nightly",
        target="linux_cron",
        deployment_file=str(artifact_path),
        trigger_config={"expression": "0 1 * * *"},
    )

    third = generate_artifacts(root=tmp_path)
    assert str(artifact_path) in third.updated


def test_generate_artifacts_target_filter_reports_mismatch(tmp_path: Path) -> None:
    _upsert_job(
        tmp_path,
        name="nightly",
        target="linux_cron",
        deployment_file=str(tmp_path / "ops" / "workflows" / "cron" / "nightly.cron"),
    )
    _upsert_job(
        tmp_path,
        name="local",
        target="local_async",
        deployment_file=str(tmp_path / ".fx" / "cron" / "deployments" / "local.toml"),
        trigger_kind="event",
        trigger_config={"kind": "manual"},
    )

    report = generate_artifacts(root=tmp_path, target="linux_cron")
    assert any("target mismatch" in item for item in report.skipped)


def test_generate_artifacts_can_render_script_execution_command(tmp_path: Path) -> None:
    artifact_path = tmp_path / "ops" / "workflows" / "cron" / "nightly.cron"
    _upsert_job(
        tmp_path,
        name="nightly",
        target="linux_cron",
        deployment_file=str(artifact_path),
    )

    generate_artifacts(
        root=tmp_path,
        job_name="nightly",
        execution_command="python app.py cron run {job} {root}",
    )

    content = artifact_path.read_text(encoding="utf-8")
    assert f"python app.py cron run nightly {tmp_path.resolve()}" in content


def test_apply_artifacts_reports_applied_and_generate_only_skips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supported_target = "windows_task_scheduler" if os.name == "nt" else "linux_cron"
    supported_file = ".xml" if supported_target == "windows_task_scheduler" else ".cron"

    _upsert_job(
        tmp_path,
        name="supported-job",
        target=supported_target,
        deployment_file=str(tmp_path / "ops" / "workflows" / f"supported{supported_file}"),
    )
    _upsert_job(
        tmp_path,
        name="local-job",
        target="local_async",
        deployment_file=str(tmp_path / ".fx" / "cron" / "deployments" / "local-job.toml"),
        trigger_kind="event",
        trigger_config={"kind": "manual"},
    )

    monkeypatch.setattr("registers.cron.adapters._run", lambda argv, cwd: None)
    report = apply_artifacts(root=tmp_path)

    assert "supported-job" in report.applied
    assert not report.errors
    assert any("local-job (local_async: generate-only)" == item for item in report.skipped)


def test_apply_artifacts_reports_host_incompatible_errors(tmp_path: Path) -> None:
    incompatible_target = "linux_cron" if os.name == "nt" else "windows_task_scheduler"
    incompatible_file = ".cron" if incompatible_target == "linux_cron" else ".xml"
    _upsert_job(
        tmp_path,
        name="incompatible-job",
        target=incompatible_target,
        deployment_file=str(tmp_path / "ops" / "workflows" / f"incompatible{incompatible_file}"),
    )

    report = apply_artifacts(root=tmp_path, target=incompatible_target)
    assert any(item.startswith("incompatible-job:") for item in report.errors)
