"""
Decorator-driven persistence registry for Pydantic models.

Quick start
-----------

::

    from pydantic import BaseModel
    from framework.db import database_registry

    @database_registry(
        "sqlite:///users.db",
        table_name="users",
        key_field="id",
        autoincrement=True,
        unique_fields=["email"],
    )
    class User(BaseModel):
        id: int | None = None
        name: str
        email: str

    # All persistence lives on the manager
    user  = User.objects.create(name="Alice", email="alice@example.com")
    users = User.objects.all()
    user.save()
    user.delete()

    # Schema helpers
    User.create_schema()
    User.schema_exists()
"""

from framework.db.decorators import database_registry
from framework.db.engine import dispose_all, dispose_engine, get_engine
from framework.db.exceptions import (
    ConfigurationError,
    DuplicateKeyError,
    ImmutableFieldError,
    InvalidPrimaryKeyAssignmentError,
    InvalidQueryError,
    MigrationError,
    ModelRegistrationError,
    RecordNotFoundError,
    RegistryError,
    RelationshipError,
    SchemaError,
    UniqueConstraintError,
)
from framework.db.registry import DatabaseRegistry
from framework.db.relations import BelongsTo, HasMany, HasManyThrough
from framework.db.schema import SchemaManager
from framework.db.metadata import RegistryConfig
from framework.db.fields import db_field
from framework.db.security import hash_password, is_password_hash, verify_password

__all__ = [
    # Core
    "database_registry",
    "DatabaseRegistry",
    "db_field",
    "hash_password",
    "is_password_hash",
    "verify_password",
    # Relationships
    "HasMany",
    "BelongsTo",
    "HasManyThrough",
    # Schema evolution
    "SchemaManager",
    # Engine management
    "get_engine",
    "dispose_engine",
    "dispose_all",
    # Config
    "RegistryConfig",
    # Exceptions
    "RegistryError",
    "ConfigurationError",
    "ModelRegistrationError",
    "SchemaError",
    "MigrationError",
    "RelationshipError",
    "DuplicateKeyError",
    "InvalidPrimaryKeyAssignmentError",
    "ImmutableFieldError",
    "UniqueConstraintError",
    "RecordNotFoundError",
    "InvalidQueryError",
]
