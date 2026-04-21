# Functionals

[![PyPI version](https://img.shields.io/pypi/v/decorates)](https://pypi.org/project/decorates/)
[![Python versions](https://img.shields.io/pypi/pyversions/decorates)](https://pypi.org/project/decorates/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Module](https://img.shields.io/badge/module-functionals-green)](#functionals)
[![CLI](https://img.shields.io/badge/module-functionals.cli-blue)](#architecture)
[![DB](https://img.shields.io/badge/module-functionals.db-darkorange)](#architecture)
[![Cron](https://img.shields.io/badge/module-functionals.cron-purple)](#architecture)
[![FX Tool](https://img.shields.io/badge/tool-fx--tool-black)](https://github.com/nexustech101/fx-tool)
![Tests](https://img.shields.io/badge/tests-200%2B%20unit%20tests-brightgreen)

Functionals is a DX-first Python framework for building:

- CLI tooling systems
- Data and API services
- Scheduled/event automation workflows

It uses decorators for command, model, and job definitions, and pairs with `fx-tool`, the project manager for scaffolding, running, validating, and operating Functionals projects.

This framework is for teams and developers who want one coherent toolkit for backend development and DevOps workflows instead of stitching together many unrelated layers. Build, manage, and deploy at the speed of thought.

## Why Functionals

- Fast setup: generate ready-to-run CLI or DB/API projects with `fx init`.
- Unified patterns: decorators for commands (`cli`), models (`db`), and jobs (`cron`).
- Operational workflow support via `fx-tool`: run, install, update, pull plugins, and manage cron runtime.
- Plugin architecture: organize command suites into modules and load them cleanly.
- Production-minded behavior: structured state, health checks, operation history, and test coverage.
- Projects that use `functionals.cli` module come with a built-in interactive shell.

## Install

```bash
pip install decorates  # Package name is `decorates`; module name is `functionals`
```

Install the project manager (`fx-tool`) as a companion:

```bash
pip install fx-tool
# or from source
pip install git+https://github.com/nexustech101/fx.git
```

You can also clone directly from the repo `nexustech101/fx`:

```bash
git clone https://github.com/nexustech101/fx.git
```

## Quick Start Guide

1. Build one CLI command with a decorator.
2. Build one DB model with a decorator.
3. Use `Model.objects` for CRUD.

### CLI in minutes

```python
from __future__ import annotations

from enum import StrEnum
from time import strftime

import functionals.cli as cli
import functionals.db as db
from functionals.db import db_field
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

    todo.title = title or ""
    todo.description = description or ""
    todo.updated_at = NOW()
    todo.save()
    return f"Updated todo ID {todo_id}."


if __name__ == "__main__":
    cli.run(
        shell_title="Todo Console",
        shell_description="Manage tasks.",
        shell_colors=None,
        shell_banner=True,
        shell_usage=True,  # Prints usage menu on startup
    )
```

`functionals.cli` also supports explicit instance-mode registries for isolated
command scopes:

```python
import functionals.cli as cli


registry = cli.CommandRegistry()


@registry.register(description="Say hello")
@registry.argument("name", type=str)
@registry.option("--hello")
def hello(name: str) -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    registry.run()
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

Or:

```bash
# Run directly for interactive mode
python todo.py
```
Interactive mode:

![Screenshot](img1.png)

`fx-tool` is the recommended way to manage Functionals projects end-to-end.
Think of it as the project operations companion for Functionals, similar to how
`pip` supports Python package workflows or how `npm` supports Node package workflows.
For full `fx` usage, see the `fx-tool` docs in the separate repo.

### Database + FastAPI in 5 minutes

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from functionals.db import (
    RecordNotFoundError,
    UniqueConstraintError,
    database_registry,
)

DB_URL = "sqlite:///shop.db"

# --- Models ---

@database_registry(DB_URL, table_name="customers", unique_fields=["email"])
class Customer(BaseModel):
    id: int | None = None
    name: str
    email: str

@database_registry(DB_URL, table_name="products")
class Product(BaseModel):
    id: int | None = None
    name: str
    price: float

@database_registry(DB_URL, table_name="orders")
class Order(BaseModel):
    id: int | None = None
    customer_id: int
    product_id: int
    quantity: int
    total: float

# --- App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    for model in (Customer, Product, Order):
        model.create_schema()
    yield
    for model in (Customer, Product, Order):
        model.objects.dispose()

app = FastAPI(lifespan=lifespan)

# --- Routes ---

@app.post("/customers", response_model=Customer, status_code=201)
def create_customer(name: str, email: str):
    return Customer.objects.create(name=name, email=email)

@app.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: int):
    return Customer.objects.require(customer_id)

@app.post("/products", response_model=Product, status_code=201)
def create_product(name: str, price: float):
    return Product.objects.create(name=name, price=price)

@app.post("/orders", response_model=Order, status_code=201)
def create_order(customer_id: int, product_id: int, quantity: int):
    product = Product.objects.require(product_id)
    return Order.objects.create(
        customer_id=customer_id,
        product_id=product_id,
        quantity=quantity,
        total=product.price * quantity,
    )

@app.get("/orders/desc", response_model=list[Order])
def list_orders_desc(limit: int = 20, offset: int = 0):  # Filter by oldest   (1, 2, 3,..., n)
    return Order.objects.filter(order_by="id", limit=limit, offset=offset)

@app.get("/orders/asc", response_model=list[Order])
def list_orders_asc(limit: int = 20, offset: int = 0):  # Filter by newest  (n,..., 3, 2, 1)
    return Order.objects.filter(order_by="-id", limit=limit, offset=offset)
```

```bash
# POST /customers
curl -X POST "http://localhost:8000/customers" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@example.com"}'

# Response
{"id": 1, "name": "Alice Johnson", "email": "alice@example.com"}


# GET /customers/1
curl "http://localhost:8000/customers/1"

# Response
{"id": 1, "name": "Alice Johnson", "email": "alice@example.com"}


# POST /products
curl -X POST "http://localhost:8000/products" \
  -H "Content-Type: application/json" \
  -d '{"name": "Wireless Keyboard", "price": 49.99}'

# Response
{"id": 1, "name": "Wireless Keyboard", "price": 49.99}


# POST /orders
curl -X POST "http://localhost:8000/orders" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 1, "product_id": 1, "quantity": 2}'

# Response
{"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}


# GET /orders/asc  (oldest first)
curl "http://localhost:8000/orders/asc?limit=20&offset=0"

# Response
[
  {"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}
]


# GET /orders/desc  (newest first)
curl "http://localhost:8000/orders/desc?limit=20&offset=0"

# Response
[
  {"id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "total": 99.98}
]
```

## Cron + Workflow Operations

Use `functionals.cron` decorators to define interval/cron/event jobs.
For runtime lifecycle and workflow operations (`start`, `status`, `generate`,
`apply`, `register`, `run-workflow`), use `fx-tool`.

Both cron registration styles are supported:

```python
# Module-level style
import functionals.cron as cron

@cron.job(
    name="nightly",
    trigger=cron.cron("0 2 * * *"),
    target="local_async",
    retry_policy="exponential",
    retry_max_attempts=5,
    retry_backoff_seconds=10,
    retry_max_backoff_seconds=180,
    retry_jitter_seconds=2,
)
def nightly() -> str:
    return "ok"
```

```python
# Explicit instance style
from functionals.cron import CronRegistry

cron = CronRegistry()

@cron.job(
    name="nightly",
    trigger=cron.cron("0 2 * * *"),
    target="local_async",
    retry_policy="fixed",
    retry_max_attempts=3,
    retry_backoff_seconds=15,
)
def nightly() -> str:
    return "ok"
```

Retry-capable jobs are moved to `dead_letter` state when max attempts are exhausted.

## Architecture

- `functionals.cli`
  Decorator-driven command registration (module facade + explicit registry instances), parser/dispatch, interactive shell, and plugin loading.

- `functionals.db`
  Decorator-driven persistence for Pydantic models with SQLAlchemy-backed storage and model manager patterns.

- `functionals.cron`
  Decorator-driven interval/cron/event jobs with async runtime and deployment artifact generation.

- `fx-tool` (separate package)
  Project manager and operations CLI for Functionals workflows (scaffolding, runtime ops, cron lifecycle, and workflow orchestration).

## Who This Is For

- Backend engineers building internal tools and service utilities.
- Platform and DevOps engineers standardizing automation workflows.
- Teams building plugin-based command ecosystems for shared operations.
- AI tooling teams that need a clear path from local workflows to managed automation.
- Any engineer who needs a fast and robust solution to data intensive applications.

## Documentation

- Project architecture spec: `PROJECT_SPEC.md`
- CLI manual: `src/functionals/cli/USAGE.md`
- DB manual: `src/functionals/db/USAGE.md`
- FX tool docs (separate package): `https://github.com/nexustech101/fx-tool`
- Cron manual: `src/functionals/cron/USAGE.md` (if present in your version)

## Roadmap and Planned Extensions

Functionals is production-ready today and actively expanding into agentic tooling workflows. Planned additions include:

- MCP support:
  A decorator-based framework for defining and operating MCP servers.

- Worktree data capabilities:
  Structured storage/retrieval of project workspace state for tooling and automation contexts.

- Data-structure library for AI tooling:
  Graph and tree primitives (including knowledge graph patterns) for efficient lookup, relationship modeling, hierarchy traversal, and large-project representation.

- LLM tooling decorators:
  Decorator-driven tool definitions and memory/knowledge wiring for agent workflows.

These additions are designed to work with the current `fx-tool + cli + db + cron` architecture rather than replace it.

## Requirements

- Python 3.10+
- `pydantic>=2.0`
- `sqlalchemy>=2.0`

## Testing

- The default `pytest` suite includes SQLite coverage along with PostgreSQL/MySQL integration tests for rename-state behavior.
- Run Docker Desktop, or another compatible Docker engine, before executing the backend integration suite so the services in `docker-compose.test-db.yml` can boot successfully.
- The package is backed by a rigorous, production-focused test suite (200+ tests) covering unit behavior, edge cases, and multi-dialect integration scenarios.


## License

MIT
