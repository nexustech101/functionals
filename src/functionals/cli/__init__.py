"""
Decorator-driven CLI tooling.

Public, ergonomic entrypoints are module-level decorators and helpers:

    import functionals.cli as cli

    @cli.register(description="Say hello")
    @cli.argument("name")
    @cli.option("--hello")
    def hello(name: str) -> str:
        return f"Hello, {name}!"

    if __name__ == "__main__":
        cli.run()

Instance-mode is also supported for isolated command scopes:

    registry = cli.CommandRegistry()

    @registry.register(description="Say hello")
    @registry.argument("name")
    def hello(name: str) -> str:
        return f"Hello, {name}!"

    if __name__ == "__main__":
        registry.run()
"""

from functionals.cli.container import DIContainer
from functionals.cli.decorators import (
    argument,
    get_registry,
    list_commands,
    option,
    register,
    reset_registry,
    run,
    run_shell,
)
from functionals.cli.dispatcher import Dispatcher
from functionals.cli.exceptions import (
    CommandExecutionError,
    DependencyNotFoundError,
    DuplicateCommandError,
    FrameworkError,
    PluginLoadError,
    UnknownCommandError,
)
from functionals.cli.middleware import (
    MiddlewareChain,
    logging_middleware_post,
    logging_middleware_pre,
)
from functionals.cli.parser import ParseError, parse_command_args
from functionals.cli.plugins import load_plugins
from functionals.cli.registry import ArgumentEntry, CommandEntry, CommandRegistry, MISSING

__all__ = [
    # Module-level command API
    "register",
    "argument",
    "option",
    "run",
    "run_shell",
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
