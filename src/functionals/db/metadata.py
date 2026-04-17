"""
Immutable configuration for a single model registration.
Validated at decoration time so problems surface immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from functionals.db.exceptions import ConfigurationError
from functionals.db.fields import get_db_field_metadata
from functionals.db.typing_utils import annotation_is_integer, field_allows_none


@dataclass(frozen=True)
class RegistryConfig:
    """All validated options for a single :class:`DatabaseRegistry`."""

    model_cls: type[BaseModel]
    database_url: str
    table_name: str
    key_field: str
    manager_attr: str
    auto_create: bool
    autoincrement: bool
    unique_fields: tuple[str, ...]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        model_cls: type[BaseModel],
        *,
        database_url: str | Path,
        table_name: str,
        key_field: str,
        manager_attr: str,
        auto_create: bool,
        autoincrement: bool,
        unique_fields: tuple[str, ...],
    ) -> "RegistryConfig":
        fields = model_cls.model_fields

        if key_field not in fields:
            raise ConfigurationError(
                f"key_field '{key_field}' is not a field on model '{model_cls.__name__}'."
            )

        if not manager_attr.strip():
            raise ConfigurationError("manager_attr must be a non-empty string.")

        if manager_attr in ("model_fields", "model_config", "__class__"):
            raise ConfigurationError(
                f"manager_attr '{manager_attr}' conflicts with a Pydantic internal name."
            )

        unknown = [f for f in unique_fields if f not in fields]
        if unknown:
            raise ConfigurationError(
                f"unique_fields references unknown fields on '{model_cls.__name__}': "
                + ", ".join(unknown)
            )

        explicit_unique_fields = list(unique_fields)
        if len(set(explicit_unique_fields)) != len(explicit_unique_fields):
            raise ConfigurationError("unique_fields must not contain duplicates.")

        metadata_by_field = {
            field_name: get_db_field_metadata(field_info)
            for field_name, field_info in fields.items()
        }

        db_primary_fields = [
            field_name
            for field_name, field_meta in metadata_by_field.items()
            if field_meta.get("db_primary_key", False)
        ]
        if len(db_primary_fields) > 1:
            raise ConfigurationError(
                "Only one field may use db_field(primary_key=True). "
                f"Found: {', '.join(db_primary_fields)}."
            )
        if db_primary_fields and db_primary_fields[0] != key_field:
            raise ConfigurationError(
                f"db_field(primary_key=True) is set on '{db_primary_fields[0]}', "
                f"but key_field is '{key_field}'. Align these values."
            )

        non_key_autoincrement = [
            field_name
            for field_name, field_meta in metadata_by_field.items()
            if field_name != key_field and field_meta.get("db_autoincrement", False)
        ]
        if non_key_autoincrement:
            raise ConfigurationError(
                "db_field(autoincrement=True) is only supported on the key_field. "
                f"Invalid field(s): {', '.join(non_key_autoincrement)}."
            )

        effective_autoincrement = autoincrement or bool(
            metadata_by_field[key_field].get("db_autoincrement", False)
        )

        merged_unique_fields: list[str] = []
        seen_unique_fields: set[str] = set()
        for field_name in explicit_unique_fields:
            if field_name not in seen_unique_fields:
                merged_unique_fields.append(field_name)
                seen_unique_fields.add(field_name)
        for field_name, field_meta in metadata_by_field.items():
            if field_meta.get("db_unique", False) and field_name not in seen_unique_fields:
                merged_unique_fields.append(field_name)
                seen_unique_fields.add(field_name)

        key_field_def = fields[key_field]
        key_annotation = key_field_def.annotation

        if effective_autoincrement:
            if not annotation_is_integer(key_annotation):
                raise ConfigurationError(
                    f"autoincrement requires an integer key field. "
                    f"'{key_field}' on '{model_cls.__name__}' is not an integer type."
                )
            if key_field_def.is_required() and not field_allows_none(key_field_def):
                raise ConfigurationError(
                    f"Key field '{key_field}' on '{model_cls.__name__}' uses autoincrement "
                    "but must allow None so the database can generate it. "
                    "Change the field to: id: int | None = None"
                )

        return cls(
            model_cls=model_cls,
            database_url=str(database_url),
            table_name=table_name,
            key_field=key_field,
            manager_attr=manager_attr,
            auto_create=auto_create,
            autoincrement=effective_autoincrement,
            unique_fields=tuple(merged_unique_fields),
        )
