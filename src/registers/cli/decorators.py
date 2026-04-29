"""
Public module-level decorators for ``registers.cli``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from registers.cli.registry import CommandRegistry, MISSING

_default_registry = CommandRegistry()
_active_registry: ContextVar[CommandRegistry | None] = ContextVar(
    "registers.cli.active_registry",
    default=None,
)


def _resolve_registry() -> CommandRegistry:
    registry = _active_registry.get()
    return _default_registry if registry is None else registry


@contextmanager
def use_registry(registry: CommandRegistry):
    """
    Temporarily route module-level decorators to ``registry``.

    This enables plugin/discovery imports to register commands into an explicit
    instance while preserving default module-level behavior outside the context.
    """
    token = _active_registry.set(registry)
    try:
        yield registry
    finally:
        _active_registry.reset(token)


def argument(
    name: str,
    *,
    type: Any = str,
    help: str = "",
    default: Any = MISSING,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare an argument spec for a command function."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _resolve_registry().stage_argument(
            fn,
            name,
            arg_type=type,
            help_text=help,
            default=default,
        )
        return fn

    return decorator


def option(
    flag: str,
    *,
    help: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare a command alias token, for example ``--add`` or ``-a``."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _resolve_registry().stage_option(fn, flag, help_text=help)
        return fn

    return decorator


def alias(
    flag: str,
    *,
    help: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Alias decorator for `@option(...)`."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _resolve_registry().stage_option(fn, flag, help_text=help)
        return fn

    return decorator


def register(
    name: str | None = None,
    *,
    description: str = "",
    help: str = "",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Finalize a staged command and register it in the default registry."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _resolve_registry().finalize_command(
            fn,
            name=name,
            description=description,
            help_text=help,
        )
        return fn

    return decorator


def run(
    argv: Sequence[str] | None = None,
    *,
    print_result: bool = True,
    shell_prompt: str = "> ",
    shell_input_fn: Callable[[str], str] | None = None,
    shell_banner: bool = True,
    shell_banner_text: str | None = None,
    shell_title: str = "Decorates CLI",
    shell_description: str = "Type 'help' for shell help and 'exit' to quit.",
    shell_colors: bool | None = None,
    shell_usage: bool = False,
) -> Any:
    """Run the module-level default registry."""

    return _default_registry.run(
        argv,
        print_result=print_result,
        shell_prompt=shell_prompt,
        shell_input_fn=shell_input_fn,
        shell_banner=shell_banner,
        shell_banner_text=shell_banner_text,
        shell_title=shell_title,
        shell_description=shell_description,
        shell_colors=shell_colors,
        shell_usage=shell_usage,
    )


def run_shell(
    *,
    print_result: bool = True,
    prompt: str = "> ",
    program_name: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    banner: bool = True,
    banner_text: str | None = None,
    shell_title: str = "Decorates CLI",
    shell_description: str = "Type 'help' for shell help and 'exit' to quit.",
    colors: bool | None = None,
    shell_usage: bool = False,
) -> None:
    """Run the module-level default registry in interactive mode."""

    return _default_registry.run_shell(
        print_result=print_result,
        prompt=prompt,
        program_name=program_name,
        input_fn=input_fn,
        banner=banner,
        banner_text=banner_text,
        shell_title=shell_title,
        shell_description=shell_description,
        colors=colors,
        shell_usage=shell_usage,
    )


def list_commands() -> None:
    """Print commands registered on the module-level default registry."""

    _default_registry.list_commands()


def get_registry() -> CommandRegistry:
    """Return the active registry in context, else the module default."""

    return _resolve_registry()


def reset_registry() -> None:
    """Clear the module-level default registry (useful for tests)."""

    _default_registry.clear()
