"""
Decorator-driven CLI tooling.

Public, ergonomic entrypoints are module-level decorators and helpers:

    import decorates.cli as cli

    @cli.register(description="Say hello")
    @cli.argument("name")
    @cli.option("--hello")
    def hello(name: str) -> str:
        return f"Hello, {name}!"

    if __name__ == "__main__":
        cli.run()
"""

from decorates.cli.container import DIContainer
from decorates.cli.decorators import (
    argument,
    get_registry,
    list_commands,
    option,
    register,
    reset_registry,
    run,
)
from decorates.cli.dispatcher import Dispatcher
from decorates.cli.exceptions import (
    CommandExecutionError,
    DependencyNotFoundError,
    DuplicateCommandError,
    FrameworkError,
    PluginLoadError,
    UnknownCommandError,
)
from decorates.cli.middleware import (
    MiddlewareChain,
    logging_middleware_post,
    logging_middleware_pre,
)
from decorates.cli.parser import ParseError, parse_command_args
from decorates.cli.plugins import load_plugins
from decorates.cli.registry import ArgumentEntry, CommandEntry, CommandRegistry, MISSING

__all__ = [
    # Module-level command API
    "register",
    "argument",
    "option",
    "run",
    "list_commands",
    "get_registry",
    "reset_registry",

    # Internal / advanced surfaces
    "CommandRegistry",
    "CommandEntry",
    "ArgumentEntry",
    "MISSING",
    "parse_command_args",
    "ParseError",

    # Legacy advanced runtime components
    "DIContainer",
    "Dispatcher",
    "MiddlewareChain",
    "load_plugins",
    "logging_middleware_pre",
    "logging_middleware_post",

    # Exceptions
    "CommandExecutionError",
    "DependencyNotFoundError",
    "DuplicateCommandError",
    "FrameworkError",
    "PluginLoadError",
    "UnknownCommandError",
]
