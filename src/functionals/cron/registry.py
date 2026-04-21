"""
Decorator-oriented cron job registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any


VALID_EVENT_KINDS = {"manual", "file_change", "webhook"}
VALID_TARGETS = {
    "local_async",
    "linux_cron",
    "windows_task_scheduler",
    "github_actions",
}
VALID_RETRY_POLICIES = {"none", "fixed", "exponential"}


@dataclass(frozen=True)
class TriggerSpec:
    kind: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JobEntry:
    name: str
    handler: Any
    handler_module: str
    handler_qualname: str
    trigger: TriggerSpec
    target: str
    deployment_file: str
    enabled: bool
    max_runtime: int
    tags: tuple[str, ...]
    overlap_policy: str = "skip"
    retry_policy: str = "none"
    retry_max_attempts: int = 0
    retry_backoff_seconds: float = 0.0
    retry_max_backoff_seconds: float = 0.0
    retry_jitter_seconds: float = 0.0


class CronRegistry:
    """Registry that stores job metadata captured by ``@cron.job``."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobEntry] = {}

    def register(
        self,
        fn: Any,
        *,
        name: str | None,
        trigger: TriggerSpec,
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
    ) -> JobEntry:
        if not callable(fn):
            raise TypeError("job() can only decorate callable functions.")
        if not isinstance(trigger, TriggerSpec):
            raise TypeError("job() requires a trigger created by cron.interval/cron.cron/cron.event.")

        entry_name = (name or "").strip() or fn.__name__.replace("_", "-")
        if not entry_name:
            raise ValueError("job() requires a non-empty job name.")
        if entry_name in self._jobs:
            raise ValueError(f"Cron job '{entry_name}' is already registered.")

        normalized_target = (target or "local_async").strip().lower()
        if normalized_target not in VALID_TARGETS:
            raise ValueError(
                "target must be one of: "
                + ", ".join(sorted(VALID_TARGETS))
            )

        normalized_overlap = (overlap_policy or "skip").strip().lower()
        if normalized_overlap != "skip":
            raise ValueError("overlap_policy currently supports only 'skip'.")

        normalized_retry = (retry_policy or "none").strip().lower()
        if normalized_retry not in VALID_RETRY_POLICIES:
            raise ValueError(
                "retry_policy must be one of: "
                + ", ".join(sorted(VALID_RETRY_POLICIES))
            )
        normalized_retry_attempts = int(retry_max_attempts)
        if normalized_retry_attempts < 0:
            raise ValueError("retry_max_attempts must be >= 0.")
        if normalized_retry == "none":
            normalized_retry_attempts = 0
        elif normalized_retry_attempts == 0:
            normalized_retry_attempts = 3

        normalized_backoff = float(retry_backoff_seconds)
        normalized_backoff_max = float(retry_max_backoff_seconds)
        normalized_jitter = float(retry_jitter_seconds)
        if normalized_backoff < 0:
            raise ValueError("retry_backoff_seconds must be >= 0.")
        if normalized_backoff_max < 0:
            raise ValueError("retry_max_backoff_seconds must be >= 0.")
        if normalized_backoff_max > 0 and normalized_backoff > normalized_backoff_max:
            raise ValueError("retry_max_backoff_seconds must be >= retry_backoff_seconds.")
        if normalized_jitter < 0:
            raise ValueError("retry_jitter_seconds must be >= 0.")

        module = getattr(fn, "__module__", "") or ""
        qualname = getattr(fn, "__qualname__", "") or fn.__name__

        tag_values = tuple(tag.strip() for tag in (tags or ()) if tag and tag.strip())
        if max_runtime < 0:
            raise ValueError("max_runtime must be >= 0.")

        entry = JobEntry(
            name=entry_name,
            handler=fn,
            handler_module=module,
            handler_qualname=qualname,
            trigger=trigger,
            target=normalized_target,
            deployment_file=(deployment_file or "").strip(),
            enabled=bool(enabled),
            max_runtime=int(max_runtime),
            tags=tag_values,
            overlap_policy=normalized_overlap,
            retry_policy=normalized_retry,
            retry_max_attempts=normalized_retry_attempts,
            retry_backoff_seconds=normalized_backoff,
            retry_max_backoff_seconds=normalized_backoff_max,
            retry_jitter_seconds=normalized_jitter,
        )
        self._jobs[entry.name] = entry
        return entry
    
    # Backwards compatible with older architecture of this framework;
    # Developers can instantiate a Registry object and use `@cron.job(...)` decorators 
    # or import decorators directly.
    def job(
        self,
        name: str | None = None,
        *,
        trigger: TriggerSpec,
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

        def decorator(fn: Any) -> Any:
            self.register(
                fn,
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
            return fn
        return decorator

    def get(self, name: str) -> JobEntry:
        if name not in self._jobs:
            raise KeyError(f"No cron job registered as '{name}'.")
        return self._jobs[name]
    
    # Alias for returning an intance of this registry, for compatibility with module-level accessors
    def get_registry(self) -> CronRegistry:
        """Return the registry instance (for compatibility with module-level accessors)."""
        return self
    
    # Alias for clearing the registry, for compatibility with module-level accessors
    def reset_registry(self) -> None:
        """Clear all registered jobs from the registry (for compatibility with module-level accessors)."""
        self.clear()

    def all(self) -> dict[str, JobEntry]:
        return dict(self._jobs)

    def clear(self) -> None:
        self._jobs.clear()

    def __len__(self) -> int:
        return len(self._jobs)

    def merge_from(self, other: CronRegistry) -> int:
        """
        Merge job entries from another registry.

        Returns the number of newly added jobs. Raises ValueError when a job
        name exists in both registries with different metadata.
        """
        if other is self:
            return 0

        added = 0
        for name, entry in other.all().items():
            existing = self._jobs.get(name)
            if existing is None:
                self._jobs[name] = entry
                added += 1
                continue
            if existing != entry:
                raise ValueError(
                    f"Conflicting cron job '{name}' detected while merging registries."
                )
        return added

    @staticmethod
    def interval(*, seconds: int = 0, minutes: int = 0, hours: int = 0) -> TriggerSpec:
        """Instance-compatible helper for ``interval(...)`` trigger creation."""
        return interval(seconds=seconds, minutes=minutes, hours=hours)

    @staticmethod
    def cron(expression: str, *, timezone: str = "local") -> TriggerSpec:
        """Instance-compatible helper for ``cron(...)`` trigger creation."""
        return cron(expression, timezone=timezone)

    @staticmethod
    def event(kind: str, /, **config: Any) -> TriggerSpec:
        """Instance-compatible helper for ``event(...)`` trigger creation."""
        return event(kind, **config)


def interval(*, seconds: int = 0, minutes: int = 0, hours: int = 0) -> TriggerSpec:
    total = int(seconds) + int(minutes) * 60 + int(hours) * 3600
    if total <= 0:
        raise ValueError("interval() requires a positive duration.")
    return TriggerSpec(kind="interval", config={"seconds": total})


def _validate_cron_field(field: str, *, allow_zero: bool = True) -> None:
    if field == "*":
        return
    if field.startswith("*/") and field[2:].isdigit() and int(field[2:]) > 0:
        return
    parts = field.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            raise ValueError("cron() contains an empty field segment.")
        if not part.isdigit():
            raise ValueError(f"Unsupported cron segment '{part}'.")
        value = int(part)
        if value < (0 if allow_zero else 1):
            raise ValueError(f"Invalid cron value '{value}'.")


def cron(expression: str, *, timezone: str = "local") -> TriggerSpec:
    expr = (expression or "").strip()
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("cron() expects a 5-field expression: m h dom mon dow.")
    minute, hour, dom, mon, dow = fields
    _validate_cron_field(minute)
    _validate_cron_field(hour)
    _validate_cron_field(dom, allow_zero=False)
    _validate_cron_field(mon, allow_zero=False)
    _validate_cron_field(dow)
    return TriggerSpec(kind="cron", config={"expression": expr, "timezone": timezone})


def event(kind: str, /, **config: Any) -> TriggerSpec:
    normalized = (kind or "").strip().lower()
    if normalized not in VALID_EVENT_KINDS:
        raise ValueError(
            "event() kind must be one of: " + ", ".join(sorted(VALID_EVENT_KINDS))
        )
    if normalized == "file_change":
        paths = config.get("paths", [])
        if not isinstance(paths, (list, tuple)) or not paths:
            raise ValueError("file_change events require non-empty 'paths'.")
    if normalized == "webhook":
        path = str(config.get("path", "")).strip()
        if not path.startswith("/"):
            raise ValueError("webhook events require a 'path' starting with '/'.")
    return TriggerSpec(kind=normalized, config=dict(config))


def maybe_awaitable(result: Any) -> bool:
    return inspect.isawaitable(result)
