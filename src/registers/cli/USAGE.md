# `registers.cli` Usage Manual

This guide is intentionally exhaustive.

Goal: if an engineer or an agent reads this file, they can build production CLI
automation scripts with `registers.cli` without needing to inspect framework internals.

---

## 1. What `registers.cli` Gives You

`registers.cli` is a decorator-first CLI framework with:

- command registration by decorators
- positional + named argument parsing
- alias support (`--long` and `-s`)
- built-in help system (`help`, `--help`, `-h`)
- interactive shell mode (`--interactive`, `-i`)
- plugin discovery/import (`load_plugins`)
- isolated class-instance registries (`CommandRegistry`)
- explicit dispatch with dependency injection (`DIContainer`) and middleware (`MiddlewareChain`)

It supports two compatible architectures:

1. Module-level default facade (`import registers.cli as cli`)
2. Explicit class-instance facade (`registry = cli.CommandRegistry()`)

Both support the same command decorators and runtime behavior.

**Summary**: This section defines the full capability surface and confirms that module-level and instance-level architectures are first-class and compatible.

---

## 2. Pick an Architecture

Use module-level facade when:

- your script is a single CLI app
- commands can share one global registry

Use explicit `CommandRegistry()` when:

- you need isolated registries in one process
- you build plugin systems/tests with separate command scopes
- you want explicit runtime wiring (`registry.dispatch(...)`)

**Summary**: Choose module-level for single-surface apps, and choose instance-level when you need isolation, composability, or explicit runtime control.

---

## 3. Quick Start (Module-Level)

Create `hello.py`:

```python
from __future__ import annotations

import registers.cli as cli


@cli.register(description="Greet someone")
@cli.argument("name", type=str, help="Person to greet")
@cli.option("--greet")
@cli.option("-g")
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    cli.run(
        shell_title="Hello Console",
        shell_description="Run greeting commands.",
        shell_usage=True,
    )
```

Run:

```bash
python hello.py greet Ada
python hello.py --greet Ada
python hello.py -g --name Ada
```

Expected output:

```text
Hello, Ada!
```

**Summary**: The module-level facade is the fastest path for building a standard CLI with decorators and `cli.run()`.

---

## 4. Quick Start (Explicit Instance Registry)

Create `hello_instance.py`:

```python
from __future__ import annotations

import registers.cli as cli


registry = cli.CommandRegistry()


@registry.register(description="Greet someone")
@registry.argument("name", type=str, help="Person to greet")
@registry.option("--greet")
@registry.option("-g")
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    registry.run(
        shell_title="Hello Instance Console",
        shell_description="Run greeting commands in isolated registry.",
        shell_usage=True,
    )
```

Run:

```bash
python hello_instance.py greet Ada
python hello_instance.py --greet Ada
python hello_instance.py -g --name Ada
```

Expected output:

```text
Hello, Ada!
```

Note:

- `CommandRegistry` intentionally does not expose `register` on the class itself.
- Decorators are exposed on registry instances (`registry.register`, `registry.argument`, `registry.option`).

**Summary**: Instance mode keeps the same decorator ergonomics while isolating command state from other registries.

---

## 5. Command Decorators and Naming Rules

### `@register(name=None, description="", help="")`

Finalizes a function into a command.

Name resolution rules:

1. If `name=` is provided, use it.
2. Else infer from first long option (`--add` -> command name `add`).
3. Else fallback to function name.

Example:

```python
@cli.register(description="List tasks")
@cli.option("--list")
def list_tasks() -> str:
    return "ok"
```

Command token is `list`, and alias `--list` also works.

### `@argument(name, type=str, help="", default=MISSING)`

Declares argument metadata and order.

- explicit declarations are authoritative for order/type/default/help
- undeclared function params are inferred from function signature

### `@option(flag, help="")`

Adds a command alias token, for example:

```python
@cli.option("--add")
@cli.option("-a")
```

**Summary**: Decorators define the command contract: name resolution, argument typing/defaults, and alias tokens.

---

## 6. Parsing Rules (All Supported Forms)

Given:

```python
@cli.register(name="add", description="Add todo")
@cli.argument("title", type=str, help="Title")
@cli.argument("description", type=str, default="", help="Description")
@cli.option("--add")
@cli.option("-a")
def add(title: str, description: str = "") -> str:
    return f"Added: {title} | {description}"
```

All of these are valid:

```bash
python todo.py add "Buy milk" "2%"
python todo.py --add "Buy milk" "2%"
python todo.py -a --title "Buy milk" --description "2%"
python todo.py add "Buy milk" --description "2%"
```

Expected output:

```text
Added: Buy milk | 2%
```

### Boolean argument behavior

Given:

```python
@cli.register(description="Run command")
@cli.argument("verbose", type=bool, help="Enable verbose mode")
def run(verbose: bool = False) -> str:
    return f"verbose={verbose}"
```

Run:

```bash
python app.py run
python app.py run --verbose
```

Expected output:

```text
verbose=False
verbose=True
```

### Duplicate argument behavior

Same value twice is allowed:

```bash
python app.py add "Task A" --title "Task A"
```

Different values for same arg fails:

```bash
python app.py add "Task A" --title "Task B"
```

Expected output (and exit code `2`):

```text
Error: Argument 'title' was provided multiple times with different values.
usage: app.py add <title> [<description> | --description VALUE]
```

### Unknown options

```bash
python app.py add --unknown x
```

Expected output (and exit code `2`):

```text
Error: Unknown option '--unknown'.
usage: app.py add <title> [<description> | --description VALUE]
```

**Summary**: Parsing supports positional/named/mixed forms, handles booleans as flags, and enforces deterministic conflict/error behavior.

---

## 7. Built-in Help and Suggestions

Built-in tokens are always available:

- `help`
- `--help`
- `-h`

Command examples:

```bash
python app.py help
python app.py --help
python app.py -h
python app.py help add
python app.py help --help
```

Expected output snippets:

```text
<Shell Title>
<Shell Description>

Shell builtins
  help            Show this menu
  help <command>  Show detailed help for a specific command
  commands        List all registered commands
  exec <command>  Run a system command in the host shell
  exit / quit     Leave interactive mode

Registered commands
  add      Add todo
  update   Update todo
```

For `help add`:

```text
Command: add
Description: Add todo
Usage: usage: app.py add <title> [<description> | --description VALUE]
Aliases: --add, -a
```

For `help --help`:

```text
Built-in Command: help
```

### Unknown command suggestions

```bash
python app.py ad
```

Expected output (and exit code `2`):

```text
Did you mean 'add'?
```

**Summary**: Help is built in (global + command-specific), and unknown commands provide suggestion-driven recovery.

---

## 8. Interactive Mode

### How interactive mode starts

`cli.run()` behavior:

- if no argv and stdin is a TTY: starts interactive shell
- if no argv and stdin is not a TTY: prints standard help

You can force shell mode:

```bash
python app.py --interactive
python app.py -i
```

### Interactive shell built-ins

- `help`
- `help <command>`
- `commands`
- `exec <command>`
- `exit` / `quit`

Example session:

```text
$ python app.py --interactive
Task Console
Manage tasks.

> commands
Registered commands
  add      Add todo
  update   Update todo

> help add
add
  Add todo
  Usage    usage: app.py add <title> [<description> | --description VALUE]
  Aliases  --add, -a

> add "Buy milk"
Added: Buy milk | 

> quit
Goodbye.
```

### `exec` shell command

In interactive mode:

```text
> exec echo hello world
Exec Result
  Shell: PowerShell
  Command: echo hello world
  Exit code: 0
  Stdout:
    hello world
```

If no command text:

```text
> exec
Error: 'exec' requires a command to run.
```

### Interactive configuration options

Both `cli.run(...)` and `cli.run_shell(...)` support:

- title and description branding
- prompt text
- color mode
- banner enable/disable
- startup help menu (`shell_usage=True`)

Example:

```python
cli.run(
    ["--interactive"],
    shell_title="Task Console",
    shell_description="Operate task workflows.",
    shell_banner=False,
    shell_colors=False,
    shell_usage=True,
)
```

**Summary**: Interactive mode provides a shell-native operator workflow (`help`, `commands`, `exec`, `exit`) with configurable UX controls.

---

## 9. Plugin Discovery and Loading

### Module-level loading

Project:

```text
app/
  plugins/
    __init__.py
    ping.py
main.py
```

`app/plugins/ping.py`:

```python
import registers.cli as cli


@cli.register(description="Plugin ping")
@cli.option("--ping")
def ping() -> str:
    return "pong"
```

`main.py`:

```python
import registers.cli as cli


def main() -> None:
    cli.load_plugins("app.plugins", cli.get_registry())
    cli.run()


if __name__ == "__main__":
    main()
```

Run:

```bash
python main.py ping
```

Expected output:

```text
pong
```

### Instance-level loading

```python
import registers.cli as cli

registry = cli.CommandRegistry()
registry.load_plugins("app.plugins")
registry.run()
```

This loads plugins into that registry instance only.

**Summary**: Plugin loading is registry-scoped, so you can intentionally control which command surface receives discovered plugin commands.

---

## 10. Explicit Dispatch, DI, and Middleware

This is the advanced path for non-argv runtimes, service injection, and
cross-cutting behaviors.

```python
from __future__ import annotations

import registers.cli as cli


class GreeterService:
    def greet(self, name: str) -> str:
        return f"hi:{name}"


registry = cli.CommandRegistry()


@registry.register(name="injected", description="Injected greet")
@registry.argument("name", type=str)
def injected(name: str, service: GreeterService) -> str:
    return service.greet(name)


container = cli.DIContainer()
container.register(GreeterService, GreeterService())

chain = cli.MiddlewareChain()
chain.add_pre(cli.logging_middleware_pre)
chain.add_post(cli.logging_middleware_post)

result = registry.dispatch(
    "injected",
    {"name": "Ada"},
    container=container,
    middleware=chain,
)
print(result)
```

Expected output:

```text
hi:Ada
```

If the dependency is missing:

```text
DependencyNotFoundError: No instance registered for type 'GreeterService'...
```

**Summary**: Use explicit dispatch for non-argv runtimes, typed dependency injection, and middleware-based execution hooks.

---

## 11. Module-Level and Instance-Level Isolation

Registries are isolated by design.

This pattern is useful when one process hosts multiple command surfaces, for example:

- a plugin host that runs separate command sets per tenant/workspace
- an integration test harness that executes isolated registries without global collisions
- an orchestrator that keeps "internal ops" commands separate from "user-facing" commands

Example: three registries in one script, each with its own `sync` command token.

```python
from __future__ import annotations

import sys
import registers.cli as cli

first = cli.CommandRegistry()
second = cli.CommandRegistry()

@first.register(description="First")
@first.option("--sync")
def sync_first() -> str:
    return "first"

@second.register(description="Second")
@second.option("--sync")
def sync_second() -> str:
    return "second"

@cli.register(description="Module")
@cli.option("--sync")
def sync_module() -> str:
    return "module"

def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python isolation_demo.py <first|second|module> <command> [args...]")
        return 2

    scope = sys.argv[1]
    argv = sys.argv[2:]

    if scope == "first":
        result = first.run(argv, print_result=False)
    elif scope == "second":
        result = second.run(argv, print_result=False)
    elif scope == "module":
        result = cli.run(argv, print_result=False)
    else:
        print(f"Unknown scope '{scope}'. Use first|second|module.")
        return 2

    if result is not None:
        print(result)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Run:

```bash
python isolation_demo.py first sync
python isolation_demo.py first --sync
python isolation_demo.py second sync
python isolation_demo.py second --sync
python isolation_demo.py module sync
python isolation_demo.py module --sync
```

Expected output:

```text
first
first
second
second
module
module
```

**Summary**: We isolate command surfaces so each scope (tenant, plugin set, workflow, test harness, etc.) has its own command namespace, aliases, help output, and dispatch behavior without collisions.

---

## 12. Error Model and Exit Semantics

### Registration-time errors

- duplicate command/alias -> `DuplicateCommandError`
- reserved tokens (`help`, `--help`, `-h`, `--interactive`, `-i`) -> `ValueError`
- invalid/de-duplicated argument declaration -> `ValueError`

### Runtime parse errors

For parse errors and unknown command/help targets:

- message is printed
- process exits with status `2` (`SystemExit(2)`)

### Handler errors

Unhandled handler exceptions are wrapped as:

- `CommandExecutionError("Command '<name>' failed: <reason>")`

Framework-level exceptions (`FrameworkError` subclasses) are passed through.

**Summary**: Registration failures are explicit, parse/help errors exit with code `2`, and unexpected handler failures are wrapped as `CommandExecutionError`.

---

## 13. Full Public API Surface

Primary module-level API:

- `register(...)`
- `argument(...)`
- `option(...)`
- `run(...)`
- `run_shell(...)`
- `list_commands()`
- `get_registry()`
- `reset_registry()`

Registry API:

- `registry.register(...)`
- `registry.argument(...)`
- `registry.option(...)`
- `registry.run(...)`
- `registry.run_shell(...)`
- `registry.list_commands()`
- `registry.print_help(...)`
- `registry.has(...)`
- `registry.get(...)`
- `registry.all()`
- `registry.load_plugins(...)`
- `registry.dispatch(...)`
- `registry.clear()`
- `registry.reset_registry()`
- `registry.get_registry()`
- `registry.suggest(...)`

Advanced runtime building blocks (also exported):

- `CommandEntry`
- `ArgumentEntry`
- `MISSING`
- `DIContainer`
- `Dispatcher`
- `MiddlewareChain`
- `load_plugins(package_path, registry)`
- `parse_command_args(entry, tokens)`
- `logging_middleware_pre`
- `logging_middleware_post`

Exceptions:

- `FrameworkError`
- `DuplicateCommandError`
- `UnknownCommandError`
- `DependencyNotFoundError`
- `CommandExecutionError`
- `PluginLoadError`
- `ParseError`

**Summary**: This section is the canonical public API index for both common and advanced CLI runtime integration.

---

## 14. Agent Build Recipe

When asked to "build a CLI tool that does X", follow this exact pattern.

1. Choose architecture.

- simple one-app script -> module-level `cli`
- isolated/tested/multi-runtime app -> explicit `registry`

2. Define commands.

- one function per command
- add aliases with `@option("--long")` and optionally `@option("-s")`
- define args with `@argument(...)`

3. Wire runtime entrypoint.

- module-level: `cli.run(...)`
- instance-level: `registry.run(...)`

4. Add plugin loading if commands are split across modules.

- module-level: `cli.load_plugins("pkg.plugins", cli.get_registry())`
- instance-level: `registry.load_plugins("pkg.plugins")`

5. Add DI/middleware only if needed.

- use `registry.dispatch(...)` with `DIContainer` and `MiddlewareChain`

6. Validate with these commands.

```bash
python app.py help
python app.py help <command>
python app.py <command> ...
python app.py --interactive
```

7. Confirm expected UX.

- unknown command suggests closest match
- parse errors print usage and exit `2`
- interactive shell supports `commands`, `help`, `exec`, `exit`

**Summary**: This is the build checklist agents should follow when asked to produce a CLI tool for a concrete task.

---

## 15. Production Skeletons

### A) Module-level skeleton

```python
from __future__ import annotations

import registers.cli as cli


@cli.register(description="Describe command")
@cli.argument("value", type=str, help="Input value")
@cli.option("--do")
def do(value: str) -> str:
    return f"done:{value}"


def main() -> None:
    # Optional plugin discovery:
    # cli.load_plugins("app.plugins", cli.get_registry())
    cli.run(
        shell_title="My CLI",
        shell_description="Automate operations.",
        shell_banner=True,
        shell_usage=True,
    )


if __name__ == "__main__":
    main()
```

**Summary (A)**: Use this as the baseline template for single-surface CLIs using the module-level facade.

### B) Instance-level skeleton

```python
from __future__ import annotations

import registers.cli as cli


registry = cli.CommandRegistry()


@registry.register(description="Describe command")
@registry.argument("value", type=str, help="Input value")
@registry.option("--do")
def do(value: str) -> str:
    return f"done:{value}"


def main() -> None:
    # Optional plugin discovery:
    # registry.load_plugins("app.plugins")
    registry.run(
        shell_title="My Isolated CLI",
        shell_description="Automate operations with isolated registry.",
        shell_banner=True,
        shell_usage=True,
    )


if __name__ == "__main__":
    main()
```

**Summary (B)**: Use this as the baseline template when you need isolated command registries and explicit runtime boundaries.

**Summary**: Section 15 provides copy-ready production starter templates for both supported architectures.

---

## 16. Robust Medium-Project Plugin Architecture Example

This example mirrors the pattern used in `C:\Users\charl\Documents\Python\todo`:

- domain plugins (`todo`, `users`, `ops`)
- one shared app package
- plugin-based command growth over time
- optional split into isolated command surfaces when scope gets large

### Recommended project layout

```text
src/app/
  __init__.py
  __main__.py
  app.py
  plugins/
    __init__.py
    todo/
      __init__.py
      todo.py
    users/
      __init__.py
      users.py
    ops/
      __init__.py
      ops.py
```

### Example domain plugins

`src/app/plugins/todo/todo.py`:

```python
from __future__ import annotations
import registers.cli as cli


@cli.register(description="Add todo item")
@cli.argument("title", type=str)
@cli.option("--add")
def add_todo(title: str) -> str:
    return f"todo-added:{title}"
```

`src/app/plugins/users/users.py`:

```python
from __future__ import annotations
import registers.cli as cli


@cli.register(description="Create user")
@cli.argument("email", type=str)
@cli.option("--create-user")
def create_user(email: str) -> str:
    return f"user-created:{email}"
```

`src/app/plugins/ops/ops.py`:

```python
from __future__ import annotations
import registers.cli as cli


@cli.register(description="Rotate API token")
@cli.argument("service", type=str)
@cli.option("--rotate-token")
def rotate_token(service: str) -> str:
    return f"token-rotated:{service}"
```

### Pattern A: One shared command surface (module-level growth)

Use when all domains should be available from one CLI namespace.

`src/app/app.py`:

```python
from __future__ import annotations

import registers.cli as cli


def main() -> None:
    cli.load_plugins("app.plugins.todo", cli.get_registry())
    cli.load_plugins("app.plugins.users", cli.get_registry())
    cli.load_plugins("app.plugins.ops", cli.get_registry())

    cli.run(
        shell_title="Control Plane Console",
        shell_description="Todo + Users + Ops commands in one surface.",
        shell_usage=True,
    )


if __name__ == "__main__":
    main()
```

Run:

```bash
python -m app add "Buy milk"
python -m app create-user "ada@example.com"
python -m app rotate-token "billing-api"
```

Expected output:

```text
todo-added:Buy milk
user-created:ada@example.com
token-rotated:billing-api
```

### Pattern B: Split command surfaces (scoped registries)

Use when different teams/scopes should not share one command namespace.

`src/app/app.py`:

```python
from __future__ import annotations

import sys
from registers.cli import CommandRegistry


def _build_registry(package_path: str) -> CommandRegistry:
    registry = CommandRegistry()
    registry.load_plugins(package_path)
    return registry


_SELECT_REGISTRY_PLUGINS: dict[str, CommandRegistry] = {
    "todo" : _build_registry("app.plugins.todo"),
    "users": _build_registry("app.plugins.users"),
    "ops"  : _build_registry("app.plugins.ops"),
}


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python -m app <todo|users|ops> <command> [args...]")
        return 2

    scope = sys.argv[1]
    argv = sys.argv[2:]

    registry = _SELECT_REGISTRY_PLUGINS.get(scope)
    if registry is None:
        print(f"Unknown scope '{scope}'. Use: todo|users|ops")
        return 2

    result = registry.run(
        argv,
        print_result=False,
        shell_title=f"{scope} Console",
        shell_description=f"{scope} command surface",
        shell_usage=True,
    )
    if result is not None:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run:

```bash
python -m app todo add "Buy milk"
python -m app users create-user "ada@example.com"
python -m app ops rotate-token "billing-api"
python -m app users help
```

Expected output:

```text
todo-added:Buy milk
user-created:ada@example.com
token-rotated:billing-api
users Console
users command surface
...
Registered commands
  create-user  Create user
```

Why this scales well for medium projects:

- each domain team owns its own plugin package
- plugin loading keeps wiring explicit and composable
- you can start with Pattern A and migrate to Pattern B without rewriting command handlers
- instance registries prevent alias/command collisions across domains
- each scope can have custom shell branding and help menu

**Summary**: Use Pattern A to extend one shared CLI surface quickly; use Pattern B to split large domains into isolated command surfaces with independent registries and no namespace collisions.

---

This manual is aligned with the current `registers.cli` runtime behavior,
including module-level and class-instance architectures, parser/dispatch flows,
interactive shell behavior, plugin loading, DI/middleware execution, and error semantics.
