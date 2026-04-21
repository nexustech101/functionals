from __future__ import annotations

import sys
from pathlib import Path

import pytest

import functionals.cli as cli
from functionals.cli import DependencyNotFoundError
from functionals.cli.exceptions import DuplicateCommandError


class _Greeter:
    def greet(self, name: str) -> str:
        return f"hi:{name}"


@pytest.fixture(autouse=True)
def _reset_module_registry() -> None:
    cli.reset_registry()
    yield
    cli.reset_registry()


def _input_from_lines(lines: list[str]):
    iterator = iter(lines)

    def _read(_prompt: str) -> str:
        return next(iterator)

    return _read


def _purge_package(package_name: str) -> None:
    stale = [name for name in list(sys.modules) if name == package_name or name.startswith(f"{package_name}.")]
    for name in stale:
        sys.modules.pop(name, None)


def test_instance_decorators_register_and_run_happy_paths() -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="Greet a user")
    @registry.argument("name", type=str, help="Name to greet")
    @registry.option("--greet")
    @registry.option("-g")
    def greet(name: str) -> str:
        return f"hello:{name}"

    assert registry.has("greet")
    assert registry.get("--greet").name == "greet"
    assert registry.run(["greet", "Ada"], print_result=False) == "hello:Ada"
    assert registry.run(["--greet", "Ada"], print_result=False) == "hello:Ada"
    assert registry.run(["-g", "--name", "Ada"], print_result=False) == "hello:Ada"


def test_instance_registries_are_isolated_and_allow_same_aliases() -> None:
    first = cli.CommandRegistry()
    second = cli.CommandRegistry()

    @first.register(description="First sync")
    @first.option("--sync")
    def sync_first() -> str:
        return "first"

    @second.register(description="Second sync")
    @second.option("--sync")
    def sync_second() -> str:
        return "second"

    @cli.register(description="Module sync")
    @cli.option("--sync")
    def sync_module() -> str:
        return "module"

    assert first.run(["sync"], print_result=False) == "first"
    assert second.run(["sync"], print_result=False) == "second"
    assert cli.run(["sync"], print_result=False) == "module"


def test_instance_collision_raises_duplicate_command_error() -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="One")
    @registry.option("--add")
    def one() -> str:
        return "1"

    with pytest.raises(DuplicateCommandError):

        @registry.register(description="Two")
        @registry.option("--add")
        def two() -> str:
            return "2"


def test_instance_parse_error_paths_show_usage_and_exit(capsys) -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="Multiply")
    @registry.argument("value", type=int)
    @registry.option("--multiply")
    def multiply(value: int) -> int:
        return value * 2

    with pytest.raises(SystemExit) as exc:
        registry.run(["multiply", "bad-int"], print_result=False)

    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "Invalid value for 'value'" in out
    assert "usage:" in out

    with pytest.raises(SystemExit) as exc:
        registry.run(["multiply", "--unknown", "1"], print_result=False)

    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "Unknown option '--unknown'" in out


def test_instance_help_and_shell_paths_work(capsys) -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="Echo text")
    @registry.argument("text", type=str)
    @registry.option("--echo")
    def echo(text: str) -> str:
        return text

    assert registry.run(["help"], print_result=False) is None
    help_out = capsys.readouterr().out
    assert "Registered commands" in help_out
    assert "echo" in help_out

    registry.run_shell(
        input_fn=_input_from_lines(["echo hello", "help echo", "quit"]),
        print_result=True,
        banner=False,
        colors=False,
    )
    shell_out = capsys.readouterr().out
    assert "hello" in shell_out
    assert "Usage" in shell_out
    assert "Aliases" in shell_out


def test_instance_dispatch_supports_explicit_registry_and_container() -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="Injected greet")
    @registry.argument("name", type=str)
    @registry.option("--injected")
    def injected(name: str, service: _Greeter) -> str:
        return service.greet(name)

    container = cli.DIContainer()
    container.register(_Greeter, _Greeter())

    assert registry.dispatch("injected", {"name": "Ada"}, container=container) == "hi:Ada"

    with pytest.raises(DependencyNotFoundError):
        registry.dispatch("injected", {"name": "Ada"})


def test_instance_discovery_load_plugins_targets_explicit_registry(tmp_path: Path) -> None:
    package_name = "instance_cli_plugins"
    package_dir = tmp_path / package_name
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "alpha.py").write_text(
        "\n".join(
            [
                "import functionals.cli as cli",
                "@cli.register(description='Plugin ping')",
                "@cli.option('--ping')",
                "def ping() -> str:",
                "    return 'pong'",
            ]
        ),
        encoding="utf-8",
    )

    registry = cli.CommandRegistry()
    sys.path.insert(0, str(tmp_path))
    _purge_package(package_name)
    try:
        loaded = registry.load_plugins(package_name)
    finally:
        _purge_package(package_name)
        sys.path.pop(0)

    assert loaded
    assert registry.has("ping")
    assert registry.run(["ping"], print_result=False) == "pong"
    assert not cli.get_registry().has("ping")


def test_instance_and_module_facades_can_coexist_without_cross_registration() -> None:
    registry = cli.CommandRegistry()

    @registry.register(description="Instance command")
    @registry.option("--instance")
    def instance_cmd() -> str:
        return "instance"

    @cli.register(description="Module command")
    @cli.option("--module")
    def module_cmd() -> str:
        return "module"

    assert registry.has("instance")
    assert not registry.has("module")
    assert cli.get_registry().has("module")
    assert not cli.get_registry().has("instance")
