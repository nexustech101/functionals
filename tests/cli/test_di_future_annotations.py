from __future__ import annotations

import pytest

import decorates.cli as cli


@pytest.fixture(autouse=True)
def _reset_registry():
    cli.reset_registry()
    yield
    cli.reset_registry()


def test_inferred_arguments_resolve_future_annotations():
    @cli.register(description="Hello")
    @cli.option("--hello")
    def hello(name: "str", excited: "bool" = False) -> str:
        return f"Hello, {name}{'!' if excited else '.'}"

    assert cli.run(["hello", "Alice"], print_result=False) == "Hello, Alice."
    assert cli.run(["hello", "Alice", "--excited"], print_result=False) == "Hello, Alice!"
