from __future__ import annotations

from pathlib import Path

import pytest

from functionals.cron import CronRegistry
from functionals.cron.runtime import sync_project_jobs
from functionals.cron.state import clear_state_caches


@pytest.fixture(autouse=True)
def _reset_cron_state() -> None:
    clear_state_caches()
    yield
    clear_state_caches()


def test_registry_instance_methods_are_usable() -> None:
    registry = CronRegistry()

    @registry.job(name="instance-methods", trigger=registry.interval(seconds=30))
    def _job() -> str:
        return "ok"

    assert registry.get_registry() is registry
    assert "instance-methods" in registry.all()
    registry.reset_registry()
    assert registry.all() == {}


def test_sync_project_jobs_supports_explicit_registry_with_module_decorators(tmp_path: Path) -> None:
    src = tmp_path / "src" / "app"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "jobs.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import functionals.cron as cron",
                "@cron.job(name='default-style', trigger=cron.interval(minutes=1), target='local_async')",
                "def default_style() -> str:",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )

    custom_registry = CronRegistry()
    package, loaded, jobs = sync_project_jobs(tmp_path, registry=custom_registry)

    assert package == "app"
    assert loaded >= 2
    assert jobs == 1
    assert "default-style" in custom_registry.all()


def test_sync_project_jobs_supports_explicit_registry_with_instance_decorators(tmp_path: Path) -> None:
    src = tmp_path / "src" / "app"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "jobs.py").write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "from functionals.cron import CronRegistry",
                "cron = CronRegistry()",
                "@cron.job(name='instance-style', trigger=cron.interval(minutes=1), target='local_async')",
                "def instance_style() -> str:",
                "    return 'ok'",
            ]
        ),
        encoding="utf-8",
    )

    custom_registry = CronRegistry()
    package, loaded, jobs = sync_project_jobs(tmp_path, registry=custom_registry)

    assert package == "app"
    assert loaded >= 2
    assert jobs == 1
    assert "instance-style" in custom_registry.all()
