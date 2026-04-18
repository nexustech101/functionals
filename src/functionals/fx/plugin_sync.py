"""
Plugin pull/sync helpers for ``functionals.fx``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from functionals.fx.structure import normalize_identifier


@dataclass(frozen=True)
class SyncReport:
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()

    @property
    def synced_aliases(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.created, *self.updated]))


def sync_plugins_from_checkout(
    *,
    checkout_root: Path,
    subdir: str,
    target_plugins_dir: Path,
    force: bool = False,
) -> SyncReport:
    source_dir = (checkout_root / subdir).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(
            f"Plugin source directory '{subdir}' not found in checkout."
        )

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    target_plugins_dir.mkdir(parents=True, exist_ok=True)

    for candidate in sorted(source_dir.iterdir()):
        if not candidate.is_dir():
            continue
        if not (candidate / "__init__.py").exists():
            continue

        alias = normalize_identifier(candidate.name)
        target = target_plugins_dir / alias
        existed = target.exists()

        if existed and not force:
            skipped.append(alias)
            continue

        if existed and force:
            shutil.rmtree(target)
            updated.append(alias)
        else:
            created.append(alias)

        shutil.copytree(candidate, target)

    return SyncReport(
        created=tuple(created),
        updated=tuple(updated),
        skipped=tuple(skipped),
    )

