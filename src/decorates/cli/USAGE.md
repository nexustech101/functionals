# Building CLI Tools With `decorates.cli`

`decorates.cli` is now module-first: you define commands with module-level
decorators (`register`, `argument`, `option`) and execute them with `run()`.

## Quick Start

```python
import decorates.cli as cli


@cli.register(description="Greet someone")
@cli.argument("name", type=str, help="Person to greet")
@cli.option("--greet")
@cli.option("-g")
def greet(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    cli.run()
```

Run it like:

```bash
python app.py greet Alice
python app.py --greet Alice
python app.py -g Alice
```

## Command Decorators

### `@register(...)`

Finalizes a function as a command.

```python
@cli.register(name="add", description="Add a todo")
```

- `name` is optional.
- If `name` is omitted, the command name is inferred from the first long option
  (`--add` -> `add`).
- If no long option exists, it falls back to the function name.

### `@argument(...)`

Defines command argument metadata.

```python
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="")
```

- Explicit `@argument` declarations are authoritative for ordering/type/help.
- Any function params without `@argument` still work via annotation/default
  inference.

### `@option(...)`

Adds command aliases.

```python
@cli.option("--add")
@cli.option("-a")
```

These aliases are valid for the command token:

```bash
python todo.py add "Buy groceries"
python todo.py --add "Buy groceries"
python todo.py -a "Buy groceries"
```

## Parsing Behavior

For non-boolean arguments, both positional and named forms are supported:

```bash
python todo.py add "Read a book" "Start to finish"
python todo.py add --title "Read a book" --description "Start to finish"
python todo.py add "Read a book" --description "Start to finish"
```

Boolean arguments are flag-style:

```bash
python app.py run --verbose
```

If the same argument is passed twice with different values, parsing fails.

## Runtime Helpers

- `cli.run(argv=None, print_result=True)` executes the default module registry.
- `cli.list_commands()` prints registered commands and aliases.
- `cli.reset_registry()` clears registry state (useful in tests).

## Error Handling

- Unknown command: prints suggestion when available and exits with status `2`.
- Parse errors: prints a specific error + command usage and exits with status `2`.
- Handler crashes: wrapped as `CommandExecutionError` with exception chaining.
