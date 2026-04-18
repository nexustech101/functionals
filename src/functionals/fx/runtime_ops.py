"""
Runtime/process helpers for ``functionals.fx`` commands.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Sequence
import venv

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm as _tqdm
except Exception:  # pragma: no cover - optional dependency
    _tqdm = None


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int


class _NullProgress:
    def update(self, _: int = 1) -> None:
        return None

    def set_postfix_str(self, _: str) -> None:
        return None

    def close(self) -> None:
        return None


def run_command(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    completed = subprocess.run(list(argv), cwd=str(cwd) if cwd is not None else None)
    return CommandResult(tuple(str(part) for part in argv), int(completed.returncode))


def run_checked(argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
    result = run_command(argv, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(result.argv)}"
        )
    return result


def _stderr_is_tty() -> bool:
    stream = getattr(sys, "stderr", None)
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except Exception:
        return False


@contextmanager
def progress_steps(*, total: int, desc: str) -> Iterator[Any]:
    if total <= 0 or _tqdm is None or not _stderr_is_tty():
        yield _NullProgress()
        return

    progress = _tqdm(total=total, desc=desc, unit="step", leave=False, dynamic_ncols=True)
    try:
        yield progress
    finally:
        progress.close()


def normalize_extras(extras: str) -> str:
    parts = [part.strip() for part in extras.split(",") if part.strip()]
    return ",".join(parts)


def editable_install_target(root: Path, extras: str = "") -> str:
    target = str(root.resolve())
    normalized = normalize_extras(extras)
    if not normalized:
        return target
    return f"{target}[{normalized}]"


def _venv_python_path(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def ensure_venv_python(root: Path, venv_path: str) -> Path:
    if not venv_path.strip():
        return Path(sys.executable)

    candidate = Path(venv_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()

    if not candidate.exists():
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(str(candidate))

    python_path = _venv_python_path(candidate)
    if not python_path.exists():
        raise FileNotFoundError(f"Virtualenv python not found at {python_path}")
    return python_path


@dataclass(frozen=True)
class CloneResult:
    repo_path: Path


def clone_repo(*, repo_url: str, ref: str = "main") -> CloneResult:
    checkout_dir = Path(tempfile.mkdtemp(prefix="fx-pull-")).resolve()
    run_checked(
        ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(checkout_dir)]
    )
    return CloneResult(repo_path=checkout_dir)
