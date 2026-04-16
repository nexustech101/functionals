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

## Example 2

Absolutely. Here’s a cleaner, more professional version with less repetition and clearer command names.

```python
from __future__ import annotations

from enum import StrEnum
from time import strftime

import decorates.cli as cli
import decorates.db as db
from decorates.db import db_field
from pydantic import BaseModel

DB_PATH = "todos.db"
TABLE = "todos"
NOW = lambda: strftime("%Y-%m-%d %H:%M:%S")


class TodoStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


@db.database_registry(DB_PATH, table_name=TABLE, key_field="id")
class TodoItem(BaseModel):
    id: int | None = None
    title: str = db_field(index=True)
    description: str = db_field(default="")
    status: TodoStatus = db_field(default=TodoStatus.PENDING.value)
    created_at: str = db_field(default_factory=NOW)
    updated_at: str = db_field(default_factory=NOW)


@cli.register(name="add", description="Create a todo item")
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="", help="Todo description")
@cli.option("--add")
@cli.option("-a")
def add_todo(title: str, description: str = "") -> str:
    todo = TodoItem(title=title, description=description)
    todo.save()
    return f"Added: {todo.title} (ID: {todo.id})"


@cli.register(name="list", description="List todo items")
@cli.option("--list")
@cli.option("-l")
def list_todos() -> str:
    todos = TodoItem.objects.all()
    if not todos:
        return "No todo items found."
    return "\n".join(f"{t.id}: {t.title} [{t.status}]" for t in todos)


@cli.register(name="complete", description="Mark a todo item as completed")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.option("--complete")
@cli.option("-c")
def complete_todo(todo_id: int) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    todo.status = TodoStatus.COMPLETED.value
    todo.updated_at = NOW()
    todo.save()
    return f"Completed todo ID {todo_id}."


@cli.register(name="update", description="Update a todo item")
@cli.argument("todo_id", type=int, help="Todo ID")
@cli.argument("title", type=str, default=None, help="New title")
@cli.argument("description", type=str, default=None, help="New description")
@cli.option("--update")
@cli.option("-u")
def update_todo(todo_id: int, title: str | None = None, description: str | None = None) -> str:
    todo = TodoItem.objects.get(id=todo_id)
    if not todo:
        return f"Todo item with ID {todo_id} not found."

    if title is not None:
        todo.title = title
    if description is not None:
        todo.description = description

    todo.updated_at = NOW()
    todo.save()
    return f"Updated todo ID {todo_id}."


if __name__ == "__main__":
    cli.run()
```

Run it as follows:

```bash
# Add
python todo.py add "Buy groceries" "Milk, eggs, bread"
python todo.py --add "Buy groceries" "Milk, eggs, bread"
python todo.py -a "Buy groceries" "Milk, eggs, bread"
python todo.py add --title "Buy groceries" --description "Milk, eggs, bread"

# List
python todo.py list
python todo.py --list
python todo.py -l

# Complete
python todo.py complete 1
python todo.py --complete 1
python todo.py -c 1

# Update
python todo.py update 1 "Read two books" "Finish both novels this week"
python todo.py update 1 --title "Read two books" --description "Finish both novels this week"
python todo.py --update 1 --title "Read two books"
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
- Built-in help command is always available: `help`, `--help`, and `-h`.

## Error Handling

- Unknown command: prints suggestion when available and exits with status `2`.
- Parse errors: prints a specific error + command usage and exits with status `2`.
- Handler crashes: wrapped as `CommandExecutionError` with exception chaining.
