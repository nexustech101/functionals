"""
Public decorator API for ``registers.cron``.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from registers.cron.registry import CronRegistry, TriggerSpec


_default_registry = CronRegistry()  # Singleton registry instance for the module
_active_registry: ContextVar[CronRegistry | None] = ContextVar(
    "registers.cron.active_registry",
    default=None,
)


def _resolve_registry() -> CronRegistry:
    registry = _active_registry.get()
    return _default_registry if registry is None else registry


@contextmanager
def use_registry(registry: CronRegistry):
    """
    Temporarily route module-level decorators to ``registry``.

    This preserves module-level ergonomics while supporting isolated import/discovery.
    """
    token = _active_registry.set(registry)
    try:
        yield registry
    finally:
        _active_registry.reset(token)


def job(
    _fn: Any = None,
    name: str | None = None,
    *,
    trigger: TriggerSpec | None = None,
    target: str = "local_async",
    deployment_file: str = "",
    enabled: bool = True,
    max_runtime: int = 0,
    tags: tuple[str, ...] | list[str] | None = None,
    overlap_policy: str = "skip",
    retry_policy: str = "none",
    retry_max_attempts: int = 0,
    retry_backoff_seconds: float = 0.0,
    retry_max_backoff_seconds: float = 0.0,
    retry_jitter_seconds: float = 0.0,
):
    """Register a decorated callable as a cron job."""

    return _resolve_registry().job(
        _fn,
        name=name,
        trigger=trigger,
        target=target,
        deployment_file=deployment_file,
        enabled=enabled,
        max_runtime=max_runtime,
        tags=tags,
        overlap_policy=overlap_policy,
        retry_policy=retry_policy,
        retry_max_attempts=retry_max_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_max_backoff_seconds=retry_max_backoff_seconds,
        retry_jitter_seconds=retry_jitter_seconds,
    )


def watch(
    paths: str | Path | list[str | Path] | tuple[str | Path, ...],
    _fn: Any = None,
    *,
    name: str | None = None,
    debounce_seconds: float = 2.0,
    recursive: bool = True,
    ignore_patterns: tuple[str, ...] | list[str] | None = None,
    ignore_directories: bool = False,
    target: str = "local_async",
    deployment_file: str = "",
    enabled: bool = True,
    max_runtime: int = 0,
    tags: tuple[str, ...] | list[str] | None = None,
    overlap_policy: str = "skip",
    retry_policy: str = "none",
    retry_max_attempts: int = 0,
    retry_backoff_seconds: float = 0.0,
    retry_max_backoff_seconds: float = 0.0,
    retry_jitter_seconds: float = 0.0,
):
    """Register a file-change job."""

    return _resolve_registry().watch(
        paths,
        _fn,
        name=name,
        debounce_seconds=debounce_seconds,
        recursive=recursive,
        ignore_patterns=ignore_patterns,
        ignore_directories=ignore_directories,
        target=target,
        deployment_file=deployment_file,
        enabled=enabled,
        max_runtime=max_runtime,
        tags=tags,
        overlap_policy=overlap_policy,
        retry_policy=retry_policy,
        retry_max_attempts=retry_max_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_max_backoff_seconds=retry_max_backoff_seconds,
        retry_jitter_seconds=retry_jitter_seconds,
    )


def run(
    job_name: str,
    *,
    payload: dict[str, Any] | None = None,
    root: str | Path = ".",
    registry: CronRegistry | None = None,
) -> Any:
    """Run one cron job immediately."""

    active = _resolve_registry() if registry is None else registry
    return active.run(job_name, payload=payload, root=root)


def register(
    job_name: str | None = None,
    *,
    root: str | Path = ".",
    target: str | None = None,
    apply: bool = True,
    execution_command: str = "",
    registry: CronRegistry | None = None,
):
    """Persist cron jobs and optionally apply supported deployment artifacts."""

    active = _resolve_registry() if registry is None else registry
    return active.register(
        job_name,
        root=root,
        target=target,
        apply=apply,
        execution_command=execution_command,
    )


def start(
    *,
    root: str | Path = ".",
    workers: int = 4,
    poll_interval: float = 1.0,
    webhook_host: str = "127.0.0.1",
    webhook_port: int = 8787,
    registry: CronRegistry | None = None,
):
    """Start the foreground async cron daemon."""

    active = _resolve_registry() if registry is None else registry
    return active.start(
        root=root,
        workers=workers,
        poll_interval=poll_interval,
        webhook_host=webhook_host,
        webhook_port=webhook_port,
    )


# Utility functions to access and manage the singleton registry instance
def get_registry() -> CronRegistry:
    return _resolve_registry()


# This function is primarily for testing purposes to reset the registry state
def reset_registry() -> None:
    _default_registry.clear()
