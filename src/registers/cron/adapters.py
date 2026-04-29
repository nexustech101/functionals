"""
Deployment artifact generation and apply adapters for cron jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import subprocess

from registers.core.logging import log_exception
from registers.cron.exceptions import CronAdapterError
from registers.cron.state import CronJobRecord, cron_job_registry, parse_json, resolve_root


SUPPORTED_APPLY_TARGETS = {"linux_cron", "windows_task_scheduler"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdapterReport:
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    applied: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _default_extension(target: str) -> str:
    """Return the default file extension for a given target type."""
    if target == "linux_cron":
        return ".cron"
    if target == "windows_task_scheduler":
        return ".xml"
    if target == "github_actions":
        return ".yml"
    return ".toml"


def _resolve_deployment_path(root: Path, job: CronJobRecord) -> Path:
    """Determine the file path for a cron job's deployment artifact based on its configuration."""
    if job.deployment_file.strip():
        path = Path(job.deployment_file)
        if not path.is_absolute():
            path = (root / path).resolve()
        return path
    default_dir = root / ".fx" / "cron" / "deployments"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir / f"{job.name}{_default_extension(job.target)}"


def _execution_command(job: CronJobRecord, root: Path, execution_command: str = "") -> str:
    template = (execution_command or "fx cron trigger {job} {root}").strip()
    if "{job}" in template or "{root}" in template:
        return template.format(job=job.name, root=root)
    return f"{template} {job.name} {root}"


def _render_linux(job: CronJobRecord, root: Path, *, execution_command: str = "") -> str:
    """Render a cron job as a Linux cron entry."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "")
    if not expression and job.trigger_kind == "interval":
        seconds = int(trigger.get("seconds", 0))
        minutes = max(1, seconds // 60) if seconds > 0 else 1
        expression = f"*/{minutes} * * * *"
    if not expression:
        expression = "*/5 * * * *"
    command = f"cd {root} && {_execution_command(job, root, execution_command)}"
    return f"{expression} {command}\n"


def _render_windows(job: CronJobRecord, root: Path, *, execution_command: str = "") -> str:
    """Render a cron job as a Windows Task Scheduler entry."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "*/5 * * * *")
    command = _execution_command(job, root, execution_command)
    return "\n".join(
        [
            "<Task>",
            f"  <Name>registers-{job.name}</Name>",
            f"  <Trigger>{expression}</Trigger>",
            "  <Action>",
            "    <Command>cmd.exe</Command>",
            f"    <Arguments>/C {command}</Arguments>",
            "  </Action>",
            "</Task>",
        ]
    ) + "\n"


def _render_github_actions(job: CronJobRecord, root: Path, *, execution_command: str = "") -> str:
    """Render a cron job as a GitHub Actions workflow file."""
    trigger = parse_json(job.trigger_config, {})
    expression = trigger.get("expression", "*/15 * * * *")
    command = _execution_command(job, root, execution_command)
    return "\n".join(
        [
            f"name: {job.name}",
            "on:",
            "  workflow_dispatch: {}",
            "  schedule:",
            f"    - cron: '{expression}'",
            "jobs:",
            "  run-job:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - uses: actions/checkout@v4",
            "      - name: Trigger Functionals cron job",
            f"        run: {command}",
        ]
    ) + "\n"


def _render_local(job: CronJobRecord, root: Path, *, execution_command: str = "") -> str:
    """Render a cron job as a local configuration file."""
    return "\n".join(
        [
            "[job]",
            f"name = \"{job.name}\"",
            f"target = \"{job.target}\"",
            f"trigger_kind = \"{job.trigger_kind}\"",
            f"enabled = {str(job.enabled).lower()}",
            f"max_runtime = {job.max_runtime}",
            f"retry_policy = \"{job.retry_policy}\"",
            f"retry_max_attempts = {job.retry_max_attempts}",
            f"retry_backoff_seconds = {job.retry_backoff_seconds}",
            f"retry_max_backoff_seconds = {job.retry_max_backoff_seconds}",
            f"retry_jitter_seconds = {job.retry_jitter_seconds}",
            f"execution_command = \"{_execution_command(job, root, execution_command)}\"",
        ]
    ) + "\n"


def _render_content(job: CronJobRecord, root: Path, *, execution_command: str = "") -> str:
    """Render the content of a deployment artifact for a given cron job based on its target type."""
    if job.target == "linux_cron":
        return _render_linux(job, root, execution_command=execution_command)
    if job.target == "windows_task_scheduler":
        return _render_windows(job, root, execution_command=execution_command)
    if job.target == "github_actions":
        return _render_github_actions(job, root, execution_command=execution_command)
    return _render_local(job, root, execution_command=execution_command)


def _filter_jobs(
    rows: list[CronJobRecord],
    *,
    target: str = "",
    job_name: str = "",
) -> tuple[list[CronJobRecord], list[str]]:
    selected: list[CronJobRecord] = []
    skipped: list[str] = []
    target_value = target.strip()
    job_value = job_name.strip()
    for job in rows:
        if job_value and job.name != job_value:
            skipped.append(f"{job.name} (job mismatch)")
            continue
        if target_value and job.target != target_value:
            skipped.append(f"{job.name} (target mismatch)")
            continue
        selected.append(job)
    return selected, skipped


def generate_artifacts(
    *,
    root: str | Path = ".",
    target: str = "",
    job_name: str = "",
    execution_command: str = "",
) -> AdapterReport:
    """Generate deployment artifacts for cron jobs."""
    root_path = resolve_root(root)
    rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")

    # Track which artifacts were accessed or modified for reporting purposes
    created: list[str] = []
    updated: list[str] = []
    rows, skipped = _filter_jobs(rows, target=target, job_name=job_name)

    for job in rows:
        path = _resolve_deployment_path(root_path, job)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _render_content(job, root_path, execution_command=execution_command)
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if old == content:
                skipped.append(str(path))
            else:
                path.write_text(content, encoding="utf-8")
                updated.append(str(path))
        else:
            path.write_text(content, encoding="utf-8")
            created.append(str(path))

    return AdapterReport(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
    )


def _run(argv: list[str], *, cwd: Path) -> None:
    """Run a job and raise an error if it fails, including stderr output for debugging."""
    completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise CronAdapterError(
            f"Command failed ({completed.returncode}): {' '.join(argv)} {stderr}",
            command=argv,
            cwd=str(cwd),
            returncode=completed.returncode,
        )


def apply_artifacts(
    *,
    root: str | Path = ".",
    target: str = "",
    job_name: str = "",
    execution_command: str = "",
) -> AdapterReport:
    """Apply deployment artifacts for cron jobs."""
    root_path = resolve_root(root)
    rows = cron_job_registry(root_path).filter(project_root=str(root_path), order_by="name")
    applied: list[str] = []
    rows, _filtered_skipped = _filter_jobs(rows, target=target, job_name=job_name)
    skipped: list[str] = []
    errors: list[str] = []

    generated = generate_artifacts(
        root=root_path,
        target=target,
        job_name=job_name,
        execution_command=execution_command,
    )
    skipped.extend(generated.skipped)

    for job in rows:
        if job.target not in SUPPORTED_APPLY_TARGETS:
            skipped.append(f"{job.name} ({job.target}: generate-only)")
            continue

        path = _resolve_deployment_path(root_path, job)
        try:
            if job.target == "linux_cron":
                if os.name == "nt":
                    raise CronAdapterError("linux_cron apply is not supported on Windows hosts.", target=job.target)
                _run(["crontab", str(path)], cwd=root_path)
            elif job.target == "windows_task_scheduler":
                if os.name != "nt":
                    raise CronAdapterError(
                        "windows_task_scheduler apply is only supported on Windows hosts.",
                        target=job.target,
                    )
                _run(
                    [
                        "schtasks",
                        "/Create",
                        "/TN",
                        f"registers-{job.name}",
                        "/XML",
                        str(path),
                        "/F",
                    ],
                    cwd=root_path,
                )
            applied.append(job.name)
        except Exception as exc:
            log_exception(
                logger,
                logging.ERROR,
                "Failed to apply cron deployment artifact.",
                error=exc,
                job=job.name,
                target=job.target,
                path=str(path),
            )
            errors.append(f"{job.name}: {exc}")

    return AdapterReport(
        created=generated.created,
        updated=generated.updated,
        skipped=tuple(skipped),
        applied=tuple(applied),
        errors=tuple(errors),
    )
