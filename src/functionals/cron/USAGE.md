# `functionals.cron` Usage

`functionals.cron` is a decorator-driven scheduler and automation module built for:
- local scheduled/background jobs
- event-triggered operations (manual, file-change, webhook)
- DevOps automation where job definitions live in Python, and deployment artifacts are generated/applied via `fx`.

Use this doc as the implementation manual for building and operating job workflows.

## 1) Runtime Model

`functionals.cron` has two layers:
- Job definition layer: `@cron.job(...)` decorators register jobs.
- Runtime/operations layer: `fx cron ...` manages daemon lifecycle, execution, queueing, and deployment artifact management.
- Workflow workspace layer: centralized workflow files can be registered and executed through `fx cron`.

Default behavior:
- overlap policy: `skip` (if same job is already running, new trigger is skipped)
- retry policy: `none` (no automatic retries)
- apply model: generate first, apply explicitly

## 2) Recommended Project Layout (Centralized Jobs + Workflows)

For a clean DevOps workflow, keep job code and workflow artifacts separate but adjacent:

```text
src/app/
  __init__.py
  __main__.py
  ops/
    __init__.py
    jobs/
      __init__.py
      build.py
      deploy.py
      housekeeping.py
    scripts/
      deploy.sh
      rotate_logs.sh
ops/
  workflows/
    cron/
      nightly-maintenance.cron
    windows/
      nightly-maintenance.xml
    ci/
      nightly-maintenance.yml
```

Why this works well:
- `src/app/ops/jobs/*` is your centralized registry surface.
- `ops/workflows/*` is a centralized artifact workspace for generated deployment files.
- You can keep Python execution logic independent from target-specific deployment file formats.

## 2.1) Provisioning the Workspace

Create the centralized layout automatically:

```bash
fx cron workspace .
```

This prepares:
- `ops/workflows/cron`
- `ops/workflows/windows`
- `ops/workflows/ci`
- `ops/scripts`
- `src/app/ops/jobs`

## 3) Job Definition API

`functionals.cron` supports two compatible registration styles:
- module-level convenience (`import functionals.cron as cron`)
- explicit class instance (`cron = CronRegistry()`)

Use module-level when you want simple app wiring.
Use an explicit registry instance when you need isolated registries (tests, embedded runtimes, or multi-scope job loading).

### 3.1 Module-Level Registration (Default)

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import functionals.cron as cron


@cron.job(
    name="nightly-maintenance",
    trigger=cron.cron("0 2 * * *"),
    target="linux_cron",
    deployment_file="ops/workflows/cron/nightly-maintenance.cron",
    tags=("ops", "maintenance"),
)
def nightly_maintenance() -> str:
    subprocess.run(["bash", "src/app/ops/scripts/rotate_logs.sh"], check=True)
    return "maintenance complete"


@cron.job(
    name="build-on-change",
    trigger=cron.event("file_change", paths=["src/**/*.py"], debounce_seconds=3),
    target="local_async",
    tags=("ci", "dev"),
)
async def build_on_change() -> str:
    return "build pipeline queued"


@cron.job(
    name="deploy-webhook",
    trigger=cron.event("webhook", path="/deploy", token="replace-me"),
    target="github_actions",
    deployment_file="ops/workflows/ci/deploy-webhook.yml",
    tags=("deploy", "webhook"),
    retry_policy="exponential",
    retry_max_attempts=5,
    retry_backoff_seconds=5,
    retry_max_backoff_seconds=120,
    retry_jitter_seconds=2,
)
def deploy_webhook(event: dict) -> str:
    payload = event.get("payload", {})
    env_name = payload.get("env", "staging")
    return f"deploy requested for {env_name}"
```

### 3.2 Registry Instance Registration

```python
from __future__ import annotations

from functionals.cron import CronRegistry

cron = CronRegistry()


@cron.job(
    name="nightly-maintenance",
    trigger=cron.cron("0 2 * * *"),
    target="local_async",
    tags=("ops",),
    retry_policy="fixed",
    retry_max_attempts=3,
    retry_backoff_seconds=10,
)
def nightly_maintenance() -> str:
    return "ok"
```

### Handler Signature Notes

Jobs can be sync or async.

If present, runtime injects:
- `event`: a dict with `id`, `source`, and `payload`
- `payload`: payload dict (for convenience)

### Retry / Backoff / Dead-Letter (Both Architectures)

`@cron.job(...)` supports first-class retry controls:

- `retry_policy`: `none`, `fixed`, or `exponential`
- `retry_max_attempts`: max execution attempts including the first run
- `retry_backoff_seconds`: base delay before retry
- `retry_max_backoff_seconds`: cap for exponential backoff
- `retry_jitter_seconds`: random jitter added to delay

Module-level example:

```python
import functionals.cron as cron

@cron.job(
    name="deploy-production",
    trigger=cron.event("manual"),
    retry_policy="exponential",
    retry_max_attempts=5,
    retry_backoff_seconds=10,
    retry_max_backoff_seconds=180,
    retry_jitter_seconds=2,
)
def deploy_production(payload: dict | None = None) -> str:
    return "ok"
```

Instance-level example:

```python
from functionals.cron import CronRegistry

cron = CronRegistry()

@cron.job(
    name="deploy-production",
    trigger=cron.event("manual"),
    retry_policy="fixed",
    retry_max_attempts=3,
    retry_backoff_seconds=15,
)
def deploy_production(payload: dict | None = None) -> str:
    return "ok"
```

When retries are exhausted, the event is marked `dead_letter`.
Retry metadata is stored internally under the `__fx_retry` payload key.

### Runtime With Explicit Registry

```python
from functionals.cron import CronRegistry
from functionals.cron.runtime import sync_project_jobs, run_daemon

cron = CronRegistry()

# sync discovered jobs into state using this specific registry
sync_project_jobs(".", registry=cron)

# run daemon with this specific registry
# await run_daemon(root=".", registry=cron)
```

## 4) Trigger Types

### Interval

```python
cron.interval(seconds=30)
cron.interval(minutes=10)
cron.interval(hours=1)
```

### Cron Expression

```python
cron.cron("*/15 * * * *")  # every 15 minutes
cron.cron("0 2 * * *")     # daily at 02:00
```

### Event

```python
cron.event("manual")
cron.event("file_change", paths=["src/**/*.py"], debounce_seconds=2)
cron.event("webhook", path="/deploy", token="secret-token")
```

## 5) Targets and Deployment Behavior

Supported targets:
- `local_async`
- `linux_cron`
- `windows_task_scheduler`
- `github_actions`

Deployment behavior:
- `fx cron generate`: supported for all targets
- `fx cron apply`: currently applies for:
  - `linux_cron`
  - `windows_task_scheduler`
- CI-style targets (for example `github_actions`) are generate-only in v1

## 6) Typical DevOps Workflow (Real-World Example)

### Step 1: Define centralized jobs

Create jobs under `src/app/ops/jobs/*.py`.

### Step 1.1: Register external workflow files

If you maintain explicit deployment/workflow files, register them to the cron workspace:

```bash
# Link a workflow file to a registered cron job
fx cron register deploy-workflow . \
  --workflow-file ops/workflows/ci/deploy.yml \
  --job deploy-webhook \
  --target github_actions

# Or register a command-driven workflow (no job binding)
fx cron register db-backup . \
  --workflow-file ops/workflows/cron/db-backup.cron \
  --command "bash src/app/ops/scripts/backup.sh" \
  --target linux_cron
```

### Step 2: Start runtime daemon

```bash
fx cron start .
```

### Step 3: Verify runtime + registration

```bash
fx cron status .
fx cron jobs .
fx cron workflows .
```

### Step 4: Trigger manual operations when needed

```bash
fx cron trigger nightly-maintenance .
fx cron trigger deploy-webhook . --payload '{"env":"prod","sha":"abc123"}'

# Run a centralized registered workflow
fx cron run-workflow deploy-workflow . --payload '{"env":"prod"}'
```

### Step 5: Generate deployment artifacts

```bash
fx cron generate .
fx cron generate . --target github_actions
```

### Step 6: Apply schedules where supported

```bash
fx cron apply . --target linux_cron
fx cron apply . --target windows_task_scheduler
```

### Step 7: Observe queue and runs

```bash
fx cron status .
fx history 50 .
```

### Step 8: Stop daemon

```bash
fx cron stop .
```

## 7) Monitoring and Operations Guidance

- Use `fx cron status` for live runtime summary (PID, workers, queue/run stats).
- `fx cron status` now includes `Failed events` and `Dead-letter events` counters.
- Use `fx cron workflows` to audit linked workflow files and execution mode.
- Use `fx cron jobs` to inspect retry configuration resolved for each registered job.
- Use `fx history` for command operation history.
- Keep deployment files under `ops/workflows/` for auditability and source control.
- For sensitive webhook jobs:
  - always set a token
  - keep token in env/config, not hard-coded in committed source

## 8) Best Practices for Clean DX

- Keep all jobs in `src/app/ops/jobs/` (or equivalent) for centralized ownership.
- Keep artifact files in `ops/workflows/` to separate generated deployment files from Python code.
- Make job names explicit and stable (`nightly-maintenance`, `deploy-production`).
- Keep job handlers idempotent for safer re-triggers.
- Use tags to classify jobs (`ops`, `deploy`, `ci`, `maintenance`).

## 9) Current Limits (v1)

- Overlap behavior is fixed to `skip`.
- Retry policy is fixed to `none`.
- `fx cron apply` is implemented for Linux cron and Windows Task Scheduler adapters.
- CI targets are currently generate-only.
- Registered workflows currently support one execution mode at a time:
  - linked job enqueue (`--job`)
  - direct command execution (`--command`)
- Retry metadata is internal and stored under `__fx_retry` in event payload records.
