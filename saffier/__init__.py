__version__ = "2.0.0"

import importlib
import sys
from types import MethodType

from saffier.conf import (
    _monkay as monkay,
)
from saffier.conf import (
    add_settings_extension,
    configure_settings,
    evaluate_settings_once_ready,
    override_settings,
    reload_settings,
    settings,
    with_settings,
)
from saffier.conf.base import BaseSettings
from saffier.conf.global_settings import SaffierSettings

from . import files, marshalls
from ._instance import Instance
from .cli import Migrate
from .core.connection.database import Database, DatabaseURL
from .core.connection.registry import Registry
from .core.db import fields
from .core.db.constants import (
    CASCADE,
    DO_NOTHING,
    NEW_M2M_NAMING,
    PROTECT,
    RESTRICT,
    SET_DEFAULT,
    SET_NULL,
    ConditionalRedirect,
)
from .core.db.datastructures import Index, UniqueConstraint
from .core.db.fields import (
    BigIntegerField,
    BinaryField,
    BooleanField,
    CharChoiceField,
    CharField,
    ChoiceField,
    CompositeField,
    ComputedField,
    DateField,
    DateTimeField,
    DecimalField,
    DurationField,
    EmailField,
    ExcludeField,
    FileField,
    FloatField,
    ForeignKey,
    ImageField,
    IntegerField,
    IPAddressField,
    JSONField,
    ManyToMany,
    ManyToManyField,
    OneToOne,
    OneToOneField,
    PasswordField,
    PGArrayField,
    PlaceholderField,
    RefForeignKey,
    SmallIntegerField,
    TextField,
    TimeField,
    URLField,
    UUIDField,
)
from .core.db.models import Model, ModelRef, ReflectModel, SQLAlchemyModelMixin, StrictModel
from .core.db.models.managers import BaseManager, Manager, RedirectManager
from .core.db.querysets import Q, QuerySet, and_, not_, or_
from .core.db.querysets.prefetch import Prefetch
from .core.extras import SaffierExtra
from .core.marshalls import ConfigMarshall, Marshall, MarshallField, MarshallMethodField
from .core.signals import Signal
from .core.utils.sync import run_sync
from .engines import ModelEngine, PydanticModelEngine, get_model_engine, register_model_engine
from .exceptions import (
    DatabaseNotConnectedWarning,
    FieldDefinitionError,
    FileOperationError,
    InvalidStorageError,
    MarshallFieldDefinitionError,
    MultipleObjectsReturned,
    ObjectNotFound,
    SuspiciousFileOperation,
)


def get_migration_prepared_registry(registry: Registry | None = None) -> Registry:
    """
    Return the active registry prepared for migration templates and CLI operations.

    Saffier keeps the implementation intentionally lightweight: metadata caches are
    refreshed on the chosen registry and the active Monkay settings are evaluated
    before the registry is returned.
    """
    evaluate_settings_once_ready()
    if registry is None:
        instance = monkay.instance
        if instance is None:
            raise RuntimeError("Could not resolve the active Saffier instance.")
        registry = instance.registry
    registry.refresh_metadata(
        multi_schema=monkay.settings.multi_schema,
        ignore_schema_pattern=monkay.settings.ignore_schema_pattern,
    )
    return registry


def _package_find_missing(
    self,
    *,
    all_var: bool | object = True,
    search_pathes: object | None = None,
    ignore_deprecated_import_errors: bool = False,
    require_search_path_all_var: bool = True,
) -> dict[str, set[str]]:
    del ignore_deprecated_import_errors

    missing: dict[str, set[str]] = {}
    module = sys.modules[__name__]
    if all_var is True:
        export_names = set(__all__)
    elif all_var is False:
        export_names = set()
    else:
        export_names = set(all_var)

    for name in export_names:
        if not hasattr(module, name):
            missing.setdefault(name, set()).add("missing_attr")

    for search_path in search_pathes or ():
        module_name = (
            f"{__name__}{search_path}" if str(search_path).startswith(".") else str(search_path)
        )
        try:
            imported = importlib.import_module(module_name)
        except Exception:
            missing.setdefault(str(search_path), set()).add("search_path_import")
            continue
        if require_search_path_all_var and not hasattr(imported, "__all__"):
            missing.setdefault(str(search_path), set()).add("missing_all_var")

    return missing


__all__ = [
    "Instance",
    "get_migration_prepared_registry",
    "monkay",
    "and_",
    "not_",
    "or_",
    "Q",
    "BigIntegerField",
    "BinaryField",
    "BooleanField",
    "CASCADE",
    "ConditionalRedirect",
    "CharChoiceField",
    "CharField",
    "ChoiceField",
    "CompositeField",
    "ComputedField",
    "Database",
    "DatabaseURL",
    "DateField",
    "DateTimeField",
    "DatabaseNotConnectedWarning",
    "DecimalField",
    "DO_NOTHING",
    "DurationField",
    "ObjectNotFound",
    "EmailField",
    "ExcludeField",
    "FileField",
    "files",
    "FloatField",
    "FileOperationError",
    "ForeignKey",
    "ImageField",
    "Index",
    "IPAddressField",
    "IntegerField",
    "JSONField",
    "ManyToMany",
    "ManyToManyField",
    "BaseManager",
    "InvalidStorageError",
    "Manager",
    "Marshall",
    "MarshallField",
    "MarshallFieldDefinitionError",
    "MarshallMethodField",
    "RedirectManager",
    "Migrate",
    "ModelEngine",
    "Model",
    "ModelRef",
    "MultipleObjectsReturned",
    "NEW_M2M_NAMING",
    "OneToOne",
    "OneToOneField",
    "PasswordField",
    "PGArrayField",
    "PydanticModelEngine",
    "PlaceholderField",
    "RefForeignKey",
    "SmallIntegerField",
    "Prefetch",
    "PROTECT",
    "QuerySet",
    "RESTRICT",
    "ReflectModel",
    "Registry",
    "SET_DEFAULT",
    "SaffierExtra",
    "SaffierSettings",
    "SET_NULL",
    "Signal",
    "SQLAlchemyModelMixin",
    "StrictModel",
    "TextField",
    "TimeField",
    "UniqueConstraint",
    "URLField",
    "UUIDField",
    "configure_settings",
    "get_model_engine",
    "settings",
    "override_settings",
    "register_model_engine",
    "reload_settings",
    "fields",
    "marshalls",
    "run_sync",
    "SuspiciousFileOperation",
    "ConfigMarshall",
    "FieldDefinitionError",
    "BaseSettings",
    "add_settings_extension",
    "evaluate_settings_once_ready",
    "with_settings",
]

monkay.find_missing = MethodType(_package_find_missing, monkay)
