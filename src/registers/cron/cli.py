"""
Registers CLI integration for managing cron jobs from the defining script.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

from registers.cron.registry import CronRegistry
from registers.cron.runtime import build_event_payload
from registers.cron.state import (
    create_event,
    cron_event_registry,
    cron_job_registry,
    cron_run_registry,
    cron_runtime_registry,
    resolve_root,
)


def install_cli(
    *,
    cli_registry: Any | None = None,
    cron_registry: CronRegistry | None = None,
    command_name: str = "cron",
    root: str | Path = ".",
    execution_command: str = "",
) -> Any:
    """
    Install a ``registers.cli`` command that manages jobs in this script.

    Typical usage:

        import registers.cli as cli
        import registers.cron as cron

        @cron.job
        def rebuild() -> str:
            return "ok"

        cron.install_cli()
        cli.run()
    """

    import registers.cli as cli
    from registers.cron.decorators import get_registry

    target_cli = cli.get_registry() if cli_registry is None else cli_registry
    target_cron = get_registry() if cron_registry is None else cron_registry
    command_token = (command_name or "cron").strip()
    default_root = str(root)
    default_execution_command = execution_command or _default_execution_command(command_token)

    def cron_command(
        action: str,
        subject: str = "",
        root: str = default_root,
        payload: str = "",
        target: str = "auto",
        apply: bool = False,
        workers: int = 4,
        poll_interval: float = 1.0,
        webhook_host: str = "127.0.0.1",
        webhook_port: int = 8787,
    ) -> str:
        normalized = action.strip().lower()
        root_path = resolve_root(root)

        if normalized == "jobs":
            return _render_jobs(target_cron)

        if normalized == "run":
            job_name = _require_subject(subject, "run")
            result = target_cron.run(
                job_name,
                payload=build_event_payload(payload),
                root=root_path,
            )
            return "\n".join(
                [
                    "Cron Run Result",
                    "Status: success",
                    f"Project: {root_path}",
                    f"Job: {job_name}",
                    f"Result: {'' if result is None else result}",
                ]
            )

        if normalized == "trigger":
            job_name = _require_subject(subject, "trigger")
            target_cron.get(job_name)
            event = create_event(
                root=root_path,
                job_name=job_name,
                source="manual",
                payload=build_event_payload(payload),
                status="pending",
            )
            return "\n".join(
                [
                    "Cron Trigger Result",
                    "Status: success",
                    f"Project: {root_path}",
                    f"Job: {job_name}",
                    f"Event ID: {event.id}",
                    f"Queue status: {event.status}",
                ]
            )

        if normalized in {"register", "persist"}:
            job_name = subject.strip() or None
            report = target_cron.register(
                job_name,
                root=root_path,
                target=target,
                apply=apply,
                execution_command=default_execution_command,
            )
            return _render_register_report(report, apply=apply, execution_command=default_execution_command)

        if normalized == "status":
            return _render_status(root_path, target_cron)

        if normalized == "start":
            summary = asyncio.run(
                target_cron.start(
                    root=root_path,
                    workers=workers,
                    poll_interval=poll_interval,
                    webhook_host=webhook_host,
                    webhook_port=webhook_port,
                )
            )
            return "\n".join(
                [
                    "Cron Start Result",
                    "Status: success",
                    f"Project: {summary.root}",
                    f"Jobs: {summary.jobs}",
                    f"Workers: {summary.workers}",
                    f"Webhook enabled: {summary.webhook_enabled}",
                ]
            )

        raise ValueError(
            "Unknown cron action. Use jobs, run, trigger, register, persist, status, or start."
        )

    for name, arg_type, default, help_text in reversed(
        [
            ("action", str, None, "Action: jobs|run|trigger|register|persist|status|start"),
            ("subject", str, "", "Job name for run/trigger/register"),
            ("root", str, default_root, "Project root path"),
            ("payload", str, "", "Optional JSON payload"),
            ("target", str, "auto", "Persistence target: auto|linux_cron|windows_task_scheduler|github_actions|local_async"),
            ("apply", bool, False, "Apply generated scheduler artifacts"),
            ("workers", int, 4, "Worker count for start action"),
            ("poll_interval", float, 1.0, "Polling interval in seconds"),
            ("webhook_host", str, "127.0.0.1", "Webhook server host"),
            ("webhook_port", int, 8787, "Webhook server port"),
        ]
    ):
        kwargs = {"type": arg_type, "help": help_text}
        if default is not None:
            kwargs["default"] = default
        cron_command = target_cli.argument(name, **kwargs)(cron_command)

    cron_command = target_cli.option(f"--{command_token}")(cron_command)
    cron_command = target_cli.register(
        name=command_token,
        description="Manage cron jobs defined in this script",
    )(cron_command)
    return cron_command


def _default_execution_command(command_name: str) -> str:
    script = sys.argv[0]
    if not script or script == "-c":
        raise ValueError(
            "cron.install_cli() could not infer the script path; pass execution_command=..."
        )
    base = [sys.executable, str(Path(script).resolve()), command_name, "run", "{job}", "{root}"]
    if os.name == "nt":
        return subprocess.list2cmdline(base)
    return shlex.join(base)


def _require_subject(subject: str, action: str) -> str:
    job_name = subject.strip()
    if not job_name:
        raise ValueError(f"{action} action requires a job name.")
    return job_name


def _render_jobs(registry: CronRegistry) -> str:
    entries = registry.all()
    lines = [
        "Cron Jobs Result",
        "Status: success",
        f"Jobs: {len(entries)}",
    ]
    if entries:
        lines.append("Registered jobs:")
        for entry in entries.values():
            lines.append(
                f"  {entry.name} ({entry.trigger.kind}, target={entry.target}, enabled={entry.enabled})"
            )
    return "\n".join(lines)


def _render_register_report(report: Any, *, apply: bool, execution_command: str) -> str:
    lines = [
        "Cron Register Result",
        "Status: success",
        f"Project: {report.root}",
        f"Target: {report.target or 'default'}",
        f"Applied: {apply}",
        f"Execution command: {execution_command}",
        "Synced jobs:",
    ]
    lines.extend(f"  {name}" for name in report.synced)
    if report.generated is not None:
        lines.append(f"Generated: {len(report.generated.created) + len(report.generated.updated)}")
        lines.append(f"Skipped: {len(report.generated.skipped)}")
    if report.applied is not None:
        lines.append(f"Applied jobs: {len(report.applied.applied)}")
        lines.append(f"Apply errors: {len(report.applied.errors)}")
    return "\n".join(lines)


def _render_status(root_path: Path, registry: CronRegistry) -> str:
    runtime = cron_runtime_registry(root_path).get(project_root=str(root_path))
    runtime_status = runtime.status if runtime is not None else "stopped"
    return "\n".join(
        [
            "Cron Status Result",
            "Status: success",
            f"Project: {root_path}",
            f"Runtime: {runtime_status}",
            f"In-memory jobs: {len(registry)}",
            f"Persisted jobs: {cron_job_registry(root_path).count(project_root=str(root_path))}",
            f"Pending events: {cron_event_registry(root_path).count(project_root=str(root_path), status='pending')}",
            f"Queued events: {cron_event_registry(root_path).count(project_root=str(root_path), status='queued')}",
            f"Failed events: {cron_event_registry(root_path).count(project_root=str(root_path), status='failed')}",
            f"Runs: {cron_run_registry(root_path).count(project_root=str(root_path))}",
        ]
    )
