from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field


def db_field(
    *,
    primary_key: bool = False,
    autoincrement: bool = False,
    unique: bool = False,
    index: bool = False,
    foreign_key: str | None = None,
    **kwargs: Any,
) -> Field:
    return Field(
        json_schema_extra={
            "db_primary_key": primary_key,
            "db_autoincrement": autoincrement,
            "db_unique": unique,
            "db_index": index,
            "db_foreign_key": foreign_key,
        },
        **kwargs,
    )


def get_db_field_metadata(field_info: Any) -> dict[str, Any]:
    """Return normalized db_field metadata from a Pydantic FieldInfo object."""
    metadata = getattr(field_info, "json_schema_extra", None)
    if not isinstance(metadata, Mapping):
        return {}

    return {
        "db_primary_key": bool(metadata.get("db_primary_key", False)),
        "db_autoincrement": bool(metadata.get("db_autoincrement", False)),
        "db_unique": bool(metadata.get("db_unique", False)),
        "db_index": bool(metadata.get("db_index", False)),
        "db_foreign_key": metadata.get("db_foreign_key"),
    }
