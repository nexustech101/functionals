"""
Internal command registry for the module-level CLI decorators.

The public DX entrypoints live in ``decorates.cli.decorators``. This module
stores command specs and executes commands from those specs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
import inspect
import logging
import sys
from typing import Any, Callable, Sequence

from decorates.cli.exceptions import CommandExecutionError, DuplicateCommandError, FrameworkError, UnknownCommandError
from decorates.cli.utils.reflection import get_params
from decorates.cli.utils.typing import is_bool_flag, is_optional

logger = logging.getLogger(__name__)


class _MissingType:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _MissingType()


@dataclass(frozen=True)
class ArgumentEntry:
    """Typed metadata for one command argument."""

    name: str
    type: Any = str
    help_text: str = ""
    required: bool = True
    default: Any = MISSING


@dataclass(frozen=True)
class CommandEntry:
    """All metadata needed to parse and execute a command."""

    name: str
    handler: Callable[..., Any]
    help_text: str = ""
    description: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)
    arguments: tuple[ArgumentEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _StagedArgument:
    name: str
    arg_type: Any = str
    help_text: str = ""
    default: Any = MISSING


@dataclass(frozen=True)
class _StagedOption:
    flag: str
    help_text: str = ""


class CommandRegistry:
    """Internal state container for staged decorators and finalized commands."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandEntry] = {}
        self._aliases: dict[str, str] = {}
        self._pending_args: dict[Callable[..., Any], list[_StagedArgument]] = {}
        self._pending_options: dict[Callable[..., Any], list[_StagedOption]] = {}

    # ------------------------------------------------------------------
    # Decorator staging + finalization
    # ------------------------------------------------------------------

    def stage_argument(
        self,
        fn: Callable[..., Any],
        name: str,
        *,
        arg_type: Any = str,
        help_text: str = "",
        default: Any = MISSING,
    ) -> None:
        if not name:
            raise ValueError("argument() requires a non-empty argument name.")

        staged = self._pending_args.setdefault(fn, [])
        if any(item.name == name for item in staged):
            raise ValueError(f"Argument '{name}' was declared more than once for '{fn.__name__}'.")

        # Decorators execute bottom-up; prepend to preserve top-down source order.
        staged.insert(0, _StagedArgument(name=name, arg_type=arg_type, help_text=help_text, default=default))

    def stage_option(
        self,
        fn: Callable[..., Any],
        flag: str,
        *,
        help_text: str = "",
    ) -> None:
        if not flag or not flag.startswith("-"):
            raise ValueError("option() expects a CLI flag such as '-a' or '--add'.")

        staged = self._pending_options.setdefault(fn, [])
        if any(item.flag == flag for item in staged):
            raise ValueError(f"Option '{flag}' was declared more than once for '{fn.__name__}'.")

        # Decorators execute bottom-up; prepend to preserve top-down source order.
        staged.insert(0, _StagedOption(flag=flag, help_text=help_text))

    def finalize_command(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str = "",
        help_text: str = "",
    ) -> None:
        staged_args = self._pending_args.pop(fn, [])
        staged_options = self._pending_options.pop(fn, [])

        options = tuple(item.flag for item in staged_options)
        command_name = (name or "").strip() or self._derive_command_name(options, fn.__name__)
        if not command_name:
            raise ValueError("register() could not determine a command name.")

        summary = description or help_text
        arguments = tuple(self._build_arguments(fn, staged_args))

        self._assert_command_slot_available(command_name)
        self._assert_options_available(command_name, options)

        entry = CommandEntry(
            name=command_name,
            handler=fn,
            help_text=summary,
            description=description,
            options=options,
            arguments=arguments,
        )

        self._commands[command_name] = entry
        for flag in options:
            normalized = self._normalize_alias(flag)
            if normalized:
                self._aliases[normalized] = command_name

    # ------------------------------------------------------------------
    # Lookup + runtime
    # ------------------------------------------------------------------

    def get(self, name: str) -> CommandEntry:
        if name in self._commands:
            return self._commands[name]

        normalized = self._normalize_alias(name)
        if normalized in self._aliases:
            return self._commands[self._aliases[normalized]]

        raise UnknownCommandError(name)

    def all(self) -> dict[str, CommandEntry]:
        return dict(self._commands)

    def has(self, name: str) -> bool:
        try:
            self.get(name)
            return True
        except UnknownCommandError:
            return False

    def list_commands(self) -> None:
        if not self._commands:
            print("No commands registered.")
            return

        print("Available commands:")
        for entry in self._commands.values():
            aliases = f" [{', '.join(entry.options)}]" if entry.options else ""
            summary = entry.help_text or entry.description or "(no description)"
            print(f"  {entry.name}{aliases}: {summary}")

    def run(
        self,
        argv: Sequence[str] | None = None,
        *,
        print_result: bool = True,
    ) -> Any:
        from decorates.cli.parser import ParseError, parse_command_args, render_command_usage

        raw = list(sys.argv[1:] if argv is None else argv)
        if not raw:
            self.list_commands()
            raise SystemExit(1)

        token = raw[0]
        try:
            entry = self.get(token)
        except UnknownCommandError:
            suggestion = self._suggest(token)
            if suggestion:
                print(f"Did you mean '{suggestion}'?")
            else:
                print("Unknown command")
            raise SystemExit(2)

        try:
            kwargs = parse_command_args(entry, raw[1:])
        except ParseError as exc:
            print(f"Error: {exc}")
            print(render_command_usage(entry))
            raise SystemExit(2)

        try:
            result = entry.handler(**kwargs)
        except FrameworkError:
            raise
        except Exception as exc:
            logger.exception("Unhandled command failure in run() for '%s'.", entry.name)
            raise CommandExecutionError(entry.name, str(exc)) from exc

        if print_result and result is not None:
            print(result)

        return result

    def clear(self) -> None:
        self._commands.clear()
        self._aliases.clear()
        self._pending_args.clear()
        self._pending_options.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_alias(token: str) -> str:
        return token.lstrip("-").strip()

    def _assert_command_slot_available(self, command_name: str) -> None:
        if command_name in self._commands:
            raise DuplicateCommandError(command_name)

        if command_name in self._aliases:
            raise DuplicateCommandError(command_name)

    def _assert_options_available(self, command_name: str, options: Sequence[str]) -> None:
        for flag in options:
            normalized = self._normalize_alias(flag)
            if not normalized:
                raise ValueError(f"Invalid option '{flag}'.")

            if normalized in self._commands and normalized != command_name:
                raise DuplicateCommandError(flag)

            existing = self._aliases.get(normalized)
            if existing is not None and existing != command_name:
                raise DuplicateCommandError(flag)

    @staticmethod
    def _derive_command_name(options: Sequence[str], fallback: str) -> str:
        for flag in options:
            if flag.startswith("--") and len(flag) > 2:
                return flag[2:]
        return fallback

    def _build_arguments(
        self,
        fn: Callable[..., Any],
        staged_args: Sequence[_StagedArgument],
    ) -> list[ArgumentEntry]:
        params = get_params(fn)
        params_by_name = {param.name: param for param in params}

        for staged in staged_args:
            if staged.name not in params_by_name:
                raise ValueError(
                    f"@argument('{staged.name}') does not match any parameter on '{fn.__name__}'."
                )

        explicit_by_name = {item.name: item for item in staged_args}
        ordered: list[ArgumentEntry] = []

        # Explicit @argument entries are authoritative and preserve decorator order.
        for staged in staged_args:
            param = params_by_name[staged.name]
            annotation = self._resolve_annotation(staged.arg_type, param.annotation)
            required, default = self._resolve_requirement(
                annotation=annotation,
                param_has_default=param.has_default,
                param_default=param.default,
                explicit_default=staged.default,
            )
            ordered.append(
                ArgumentEntry(
                    name=staged.name,
                    type=annotation,
                    help_text=staged.help_text,
                    required=required,
                    default=default,
                )
            )

        # Fallback for undeclared params uses function signature inference.
        for param in params:
            if param.name in explicit_by_name:
                continue

            annotation = self._resolve_annotation(MISSING, param.annotation)
            required, default = self._resolve_requirement(
                annotation=annotation,
                param_has_default=param.has_default,
                param_default=param.default,
                explicit_default=MISSING,
            )
            ordered.append(
                ArgumentEntry(
                    name=param.name,
                    type=annotation,
                    help_text="",
                    required=required,
                    default=default,
                )
            )

        return ordered

    @staticmethod
    def _resolve_annotation(explicit_type: Any, annotation: Any) -> Any:
        if explicit_type is not MISSING:
            return explicit_type
        if annotation is inspect.Parameter.empty:
            return str
        return annotation

    @staticmethod
    def _resolve_requirement(
        *,
        annotation: Any,
        param_has_default: bool,
        param_default: Any,
        explicit_default: Any,
    ) -> tuple[bool, Any]:
        if explicit_default is not MISSING:
            return False, explicit_default

        if param_has_default:
            return False, param_default

        if is_bool_flag(annotation):
            return False, False

        if is_optional(annotation):
            return False, None

        return True, MISSING

    def _suggest(self, token: str) -> str | None:
        candidates = set(self._commands)
        candidates.update(self._aliases)
        matches = get_close_matches(self._normalize_alias(token), sorted(candidates), n=1)
        if not matches:
            return None

        guess = matches[0]
        if guess in self._aliases:
            return self._aliases[guess]
        return guess

    def __len__(self) -> int:
        return len(self._commands)

    def __repr__(self) -> str:
        names = ", ".join(self._commands)
        return f"CommandRegistry([{names}])"
