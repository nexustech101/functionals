"""
A lightweight, framework-based CLI framework.

Public API surface::

    from framework.cli import (
        CommandRegistry,
        DIContainer,
        MiddlewareChain,
        Dispatcher,
        CommandExecutionError,
        build_parser,
        load_plugins,
        logging_middleware_pre,
        logging_middleware_post,
    )
"""

from framework.cli.dispatcher import Dispatcher
from framework.cli.middleware import (
    MiddlewareChain,
    logging_middleware_post,
    logging_middleware_pre,
)
from framework.cli.parser import build_parser
from framework.cli.container import DIContainer
from framework.cli.exceptions import (
    CommandExecutionError,
    DependencyNotFoundError,
    DuplicateCommandError,
    FrameworkError,
    PluginLoadError,
    UnknownCommandError,
)
from framework.cli.registry import CommandRegistry
from framework.cli.plugins import load_plugins

__all__ = [
    # Core framework
    "CommandRegistry",
    "DIContainer",
    "Dispatcher",
    "MiddlewareChain",
    "build_parser",
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
