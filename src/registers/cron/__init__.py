"""
Decorator-driven cron/scheduler tooling for Functionals.
"""

from registers.cron.cli import install_cli
from registers.cron.decorators import (
    get_registry,
    job,
    register,
    reset_registry,
    run,
    start,
    use_registry,
    watch,
)
from registers.cron.exceptions import (
    CronAdapterError,
    CronError,
    CronLookupError,
    CronRegistrationError,
    CronRuntimeError,
    CronTriggerError,
    CronWorkspaceError,
    CronWorkspaceRuntimeError,
)
from registers.cron.registry import (
    CronRegistry,
    JobEntry,
    TriggerSpec,
    cron,
    event,
    interval,
)
from registers.cron.runtime import run_daemon, sync_project_jobs
from registers.cron.workspace import (
    ensure_workspace,
    list_workflows,
    register_workflow,
    run_registered_workflow,
)

__all__ = [
    "job",
    "watch",
    "interval",
    "cron",
    "event",
    "run",
    "register",
    "start",
    "install_cli",
    "use_registry",
    "get_registry",
    "reset_registry",
    "sync_project_jobs",
    "run_daemon",
    "ensure_workspace",
    "register_workflow",
    "list_workflows",
    "run_registered_workflow",
    "CronRegistry",
    "JobEntry",
    "TriggerSpec",
    "CronError",
    "CronRegistrationError",
    "CronTriggerError",
    "CronLookupError",
    "CronRuntimeError",
    "CronWorkspaceError",
    "CronWorkspaceRuntimeError",
    "CronAdapterError",
]
