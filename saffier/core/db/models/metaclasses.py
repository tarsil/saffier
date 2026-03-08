"""Metaclasses and metadata containers for Saffier ORM models.

This module is responsible for turning model class declarations into runtime
metadata, SQLAlchemy tables, reverse relations, and manager wiring.
"""

import contextlib
import copy
import inspect
from collections import UserDict, deque
from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Union,
    cast,
    get_origin,
)

import sqlalchemy

import saffier
from saffier.conf import settings
from saffier.core.connection.registry import Registry
from saffier.core.db import fields as saffier_fields
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.fields import BigIntegerField, Field
from saffier.core.db.models.managers import Manager, RedirectManager
from saffier.core.db.relationships.related import RelatedField
from saffier.core.db.relationships.relation import Relation
from saffier.core.signals import Broadcaster, Signal
from saffier.exceptions import ForeignKeyBadConfigured, ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model, ReflectModel


_trigger_attributes_fields_MetaInfo: set[str] = {
    "field_to_columns",
    "field_to_column_names",
    "columns_to_field",
}

_trigger_attributes_field_stats_MetaInfo: set[str] = {
    "special_getter_fields",
    "secret_fields",
    "input_modifying_fields",
}


class Fields(UserDict, dict[str, Field]):
    """Mutable field mapping that invalidates `MetaInfo` caches on change.

    `MetaInfo.fields` is not a plain dictionary because mutating the model field
    map has downstream effects on column mappings, serializer state, and cached
    tables. This wrapper updates lightweight field statistics immediately and
    invalidates the heavier caches so they are rebuilt on demand.
    """

    meta: "MetaInfo"

    def __init__(self, meta: "MetaInfo", data: dict[str, Field] | None = None) -> None:
        self.meta = meta
        super().__init__(data or {})

    def add_field_to_meta(self, name: str, field: Field) -> None:
        if not self.meta._field_stats_are_initialized:
            return
        if getattr(field, "is_computed", False):
            self.meta.special_getter_fields.add(name)
        if getattr(field, "secret", False):
            self.meta.secret_fields.add(name)
        if hasattr(field, "modify_input"):
            self.meta.input_modifying_fields.add(name)

    def discard_field_from_meta(self, name: str) -> None:
        if not self.meta._field_stats_are_initialized:
            return
        self.meta.special_getter_fields.discard(name)
        self.meta.secret_fields.discard(name)
        self.meta.input_modifying_fields.discard(name)

    def __getitem__(self, name: str) -> Field:
        return cast("Field", self.data[name])

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return key in self.data

    def __setitem__(self, name: str, value: Field) -> None:
        if name in self.data:
            self.discard_field_from_meta(name)
        self.data[name] = value
        self.add_field_to_meta(name, value)
        self.meta.invalidate(invalidate_stats=False)

    def __delitem__(self, name: str) -> None:
        if self.data.pop(name, None) is not None:
            self.discard_field_from_meta(name)
            self.meta.invalidate(invalidate_stats=False)


class FieldToColumns(UserDict, dict[str, Sequence[sqlalchemy.Column]]):
    """Lazy mapping from Saffier field names to SQLAlchemy columns.

    Some fields expand into multiple physical columns, while virtual fields have
    none at all. This mapping defers column materialization until first access so
    model initialization stays cheap.
    """

    meta: "MetaInfo"

    def __init__(self, meta: "MetaInfo") -> None:
        self.meta = meta
        super().__init__()

    def __getitem__(self, name: str) -> Sequence[sqlalchemy.Column]:
        if name in self.data:
            return cast("Sequence[sqlalchemy.Column]", self.data[name])
        field = self.meta.fields[name]
        if not field.has_column():
            result = self.data[name] = ()
            return result
        result = self.data[name] = field.get_columns(name)
        return result

    def __setitem__(self, name: str, value: Any) -> None:
        raise Exception("Cannot set item here")

    def __iter__(self) -> Any:
        self.meta.columns_to_field.init()
        return super().__iter__()

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        try:
            self[cast("str", key)]
            return True
        except KeyError:
            return False


class FieldToColumnNames(FieldToColumns, dict[str, frozenset[str]]):
    """Lazy mapping from logical field names to physical SQL column names.

    The mapping is derived from `field_to_columns` and keeps only string column
    identifiers, which is useful for serializer and payload normalization code.
    """

    def __getitem__(self, name: str) -> frozenset[str]:
        if name in self.data:
            return cast("frozenset[str]", self.data[name])
        column_names = frozenset(column.key for column in self.meta.field_to_columns[name])
        result = self.data[name] = column_names
        return result


class ColumnsToField(UserDict, dict[str, str]):
    """Reverse lookup from SQL column names to logical Saffier field names.

    The mapping is initialized lazily and raises on column collisions so Saffier
    can reliably rehydrate query rows and database payloads back into model
    fields.
    """

    meta: "MetaInfo"
    _init: bool

    def __init__(self, meta: "MetaInfo") -> None:
        self.meta = meta
        self._init = False
        super().__init__()

    def init(self) -> None:
        if self._init:
            return
        self._init = True
        columns_to_field: dict[str, str] = {}
        for field_name in self.meta.fields:
            for column_name in self.meta.field_to_column_names[field_name]:
                if column_name in columns_to_field:
                    raise ValueError(
                        f"column collision: {column_name} between field {field_name} and {columns_to_field[column_name]}"
                    )
                columns_to_field[column_name] = field_name
        self.data.update(columns_to_field)

    def __getitem__(self, name: str) -> str:
        self.init()
        return cast("str", super().__getitem__(name))

    def __setitem__(self, name: str, value: Any) -> None:
        raise Exception("Cannot set item here")

    def __contains__(self, name: object) -> bool:
        self.init()
        return super().__contains__(name)

    def __iter__(self) -> Any:
        self.init()
        return super().__iter__()

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class MetaInfo:
    """Runtime metadata container attached to every Saffier model class.

    Saffier keeps most of the expensive model bookkeeping outside the class
    dictionary itself and stores it in `MetaInfo`. That includes resolved field
    mappings, reverse relation descriptors, manager registrations, registry
    pointers, and lazily populated caches that translate between logical field
    names and physical SQLAlchemy columns.

    The container is intentionally mutable. Model construction, relation
    binding, registry copying, and dynamic schema invalidation all update the
    same `MetaInfo` instance over the lifetime of a model class.

    Attributes:
        fields (Fields):
            Mapping of declared Saffier field names to field instances.
        registry (Registry | None):
            Registry that owns the model, or `None` for detached/abstract
            models.
        foreign_key_fields (dict[str, Field]):
            Foreign-key-like fields that require reverse relation wiring.
        related_fields (dict[str, Any]):
            Reverse relation descriptors registered on related models.
        field_to_columns (FieldToColumns):
            Lazy mapping from logical field names to SQLAlchemy columns.
        columns_to_field (ColumnsToField):
            Reverse mapping from column names back to logical field names.
    """

    __slots__ = (
        "abstract",
        "fields",
        "fields_mapping",
        "registry",
        "tablename",
        "table_prefix",
        "unique_together",
        "indexes",
        "constraints",
        "foreign_key_fields",
        "parents",
        "pk",
        "one_to_one_fields",
        "many_to_many_fields",
        "pk_attribute",
        "manager",
        "model",
        "reflect",
        "managers",
        "is_multi",
        "multi_related",
        "related_names",
        "related_fields",
        "related_names_mapping",
        "signals",
        "special_getter_fields",
        "secret_fields",
        "input_modifying_fields",
        "field_to_columns",
        "field_to_column_names",
        "columns_to_field",
        "_fields_are_initialized",
        "_field_stats_are_initialized",
        "_needs_special_serialization",
    )

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._fields_are_initialized = False
        self._field_stats_are_initialized = False
        self.pk: Field | None = getattr(meta, "pk", None)
        self.pk_attribute: Field | str = getattr(meta, "pk_attribute", "")
        self.abstract: bool = getattr(meta, "abstract", False)
        self.model: type[Model] | None = None
        fields = getattr(meta, "fields", None)
        if fields is None:
            fields = getattr(meta, "fields_mapping", {})
        self.fields = dict(fields or {})
        self.registry: Registry | None = getattr(meta, "registry", None)
        self.tablename: str | None = getattr(meta, "tablename", None)
        self.table_prefix: str | None = getattr(meta, "table_prefix", None)
        self.parents: Any = getattr(meta, "parents", [])
        self.many_to_many_fields: set[str] = set(getattr(meta, "many_to_many_fields", set()))
        self.foreign_key_fields: dict[str, Any] = dict(getattr(meta, "foreign_key_fields", {}))
        self.one_to_one_fields: set[Any] = set(getattr(meta, "one_to_one_fields", set()))
        self.manager: Manager = getattr(meta, "manager", Manager())
        self.unique_together: Any = getattr(meta, "unique_together", None)
        self.indexes: Any = getattr(meta, "indexes", None)
        self.constraints: Any = getattr(meta, "constraints", None)
        self.reflect: bool = getattr(meta, "reflect", False)
        self.managers: list[str] = list(getattr(meta, "managers", []) or [])
        self.is_multi: bool = getattr(meta, "is_multi", False)
        self.multi_related: Sequence[str] = getattr(meta, "multi_related", [])
        self.related_names: set[str] = getattr(meta, "related_names", set())
        self.related_fields: dict[str, Any] = getattr(meta, "related_fields", {})
        self.related_names_mapping: dict[str, Any] = getattr(meta, "related_names_mapping", {})
        self.signals: Broadcaster | None = getattr(meta, "signals", {})  # type: ignore
        if isinstance(meta, MetaInfo):
            field_stats_initialized = object.__getattribute__(meta, "_field_stats_are_initialized")
            self.special_getter_fields = set(
                object.__getattribute__(meta, "special_getter_fields")
                if field_stats_initialized
                else ()
            )
            self.secret_fields = set(
                object.__getattribute__(meta, "secret_fields") if field_stats_initialized else ()
            )
            self.input_modifying_fields = set(
                object.__getattribute__(meta, "input_modifying_fields")
                if field_stats_initialized
                else ()
            )
            self._needs_special_serialization = object.__getattribute__(
                meta, "_needs_special_serialization"
            )
        else:
            self.special_getter_fields = set(getattr(meta, "special_getter_fields", set()) or [])
            self.secret_fields = set(getattr(meta, "secret_fields", set()) or [])
            self.input_modifying_fields = set(getattr(meta, "input_modifying_fields", set()) or [])
            self._needs_special_serialization = getattr(meta, "_needs_special_serialization", None)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "fields_mapping":
            name = "fields"
        if name == "fields":
            value = Fields(self, value)
        super().__setattr__(name, value)
        if name == "fields":
            self.invalidate()

    def __getattribute__(self, name: str) -> Any:
        if name == "fields_mapping":
            return super().__getattribute__("fields")
        if name in _trigger_attributes_fields_MetaInfo and not super().__getattribute__(
            "_fields_are_initialized"
        ):
            super().__getattribute__("init_fields_mapping")()
        if name in _trigger_attributes_field_stats_MetaInfo and not super().__getattribute__(
            "_field_stats_are_initialized"
        ):
            super().__getattribute__("init_field_stats")()
        return super().__getattribute__(name)

    def init_fields_mapping(self) -> None:
        """Initialize the lazy field and column lookup containers.

        The method is triggered on first access to any of the mapping helpers and
        prepares the objects that translate between logical field names and
        SQLAlchemy columns.
        """
        self.field_to_columns = FieldToColumns(self)
        self.field_to_column_names = FieldToColumnNames(self)
        self.columns_to_field = ColumnsToField(self)
        self._fields_are_initialized = True

    def init_field_stats(self) -> None:
        """Compute cached field statistics used by serialization and validation.

        The derived sets track computed fields, secret fields, and fields that
        may modify incoming payloads. They are rebuilt whenever the field mapping
        changes.
        """
        self.special_getter_fields = {
            field_name
            for field_name, field in self.fields.items()
            if getattr(field, "is_computed", False)
        }
        self.secret_fields = {
            field_name
            for field_name, field in self.fields.items()
            if getattr(field, "secret", False)
        }
        self.input_modifying_fields = set(self.fields.keys())
        self._field_stats_are_initialized = True

    def invalidate(
        self,
        clear_class_attrs: bool = True,
        invalidate_fields: bool = True,
        invalidate_stats: bool = True,
    ) -> None:
        """Invalidate cached metadata derived from the current field map.

        Args:
            clear_class_attrs: Whether model-level caches such as tables, PK
                metadata, and proxy models should also be cleared.
            invalidate_fields: Whether to clear field-to-column mapping caches.
            invalidate_stats: Whether to clear serializer/input statistics.
        """
        if invalidate_fields and self._fields_are_initialized:
            for attr in ("field_to_columns", "field_to_column_names", "columns_to_field"):
                with contextlib.suppress(AttributeError):
                    delattr(self, attr)
            self._fields_are_initialized = False
        if invalidate_stats:
            self.special_getter_fields = set()
            self.secret_fields = set()
            self.input_modifying_fields = set()
            self._field_stats_are_initialized = False
        if invalidate_fields or invalidate_stats:
            self._needs_special_serialization = None
        if self.model is None:
            return
        if clear_class_attrs:
            for attr in ("_table", "_pknames", "_pkcolumns", "__proxy_model__"):
                with contextlib.suppress(AttributeError):
                    delattr(self.model, attr)
            self.model._db_schemas = {}

    def full_init(self, init_column_mappers: bool = True, init_class_attrs: bool = True) -> None:
        """Eagerly initialize all lazily computed metadata structures.

        Args:
            init_column_mappers: Whether to initialize reverse column lookups.
            init_class_attrs: Whether to warm class-level table and proxy-model
                caches.
        """
        if not self._fields_are_initialized:
            self.init_fields_mapping()
        if not self._field_stats_are_initialized:
            self.init_field_stats()
        if init_column_mappers:
            self.columns_to_field.init()
        if init_class_attrs and self.model is not None:
            for attr in ("table", "pknames", "pkcolumns", "proxy_model"):
                getattr(self.model, attr)

    @property
    def needs_special_serialization(self) -> bool:
        """Return whether model dumps need custom serialization logic.

        Serialization becomes "special" when a model exposes computed fields or
        nested relations whose targets themselves require special handling. The
        result is cached until metadata invalidation occurs.

        Returns:
            bool: `True` when default flat field dumping is not sufficient.
        """
        if self._needs_special_serialization is None:
            needs_special_serialization = any(
                not self.fields[field_name].exclude for field_name in self.special_getter_fields
            )
            if not needs_special_serialization:
                for field_name in self.foreign_key_fields:
                    field = self.fields[field_name]
                    if field.exclude:
                        continue
                    target = getattr(field, "target", None)
                    if target is not None and target.meta.needs_special_serialization:
                        needs_special_serialization = True
                        break
            self._needs_special_serialization = needs_special_serialization
        return self._needs_special_serialization

    def get_columns_for_name(self, name: str) -> Sequence[sqlalchemy.Column]:
        if name in self.field_to_columns:
            return self.field_to_columns[name]
        if self.model is not None and name in self.model.table.columns:
            return (self.model.table.columns[name],)
        return ()


def _is_sqlalchemy_compatibility_enabled(model_class: type) -> bool:
    """Check whether SQLAlchemy-style class attribute access is enabled.

    Saffier can expose proxy-model attribute lookup compatible with SQLAlchemy's
    declarative style. The flag is inherited, so the full MRO is inspected.

    Args:
        model_class: Model class being inspected.

    Returns:
        bool: `True` when compatibility mode is enabled for the class.
    """
    for base in type.__getattribute__(model_class, "__mro__"):
        if base.__dict__.get("__saffier_sqlalchemy_compatibility__", False):
            return True
    return False


def _check_model_inherited_registry(bases: tuple[type, ...]) -> Registry:
    """Resolve a missing registry by inheriting the first registry from the bases.

    Concrete models may omit `Meta.registry` when inheriting from another
    concrete Saffier model. This helper mirrors that inheritance behavior by
    scanning the base classes in method-resolution order until it finds a model
    metadata object with an attached registry.

    Args:
        bases: Base classes declared for the model being constructed.

    Returns:
        Registry: The first registry inherited from the model bases.

    Raises:
        ImproperlyConfigured: If no base model contributes a registry.
    """
    found_registry: Registry | None = None

    for base in bases:
        meta: MetaInfo = getattr(base, "meta", None)  # type: ignore
        if not meta:
            continue

        if getattr(meta, "registry", None) is not None:
            found_registry = meta.registry
            break

    if not found_registry:
        raise ImproperlyConfigured(
            "Registry for the table not found in the Meta class or any of the superclasses. You must set the registry in the Meta."
        )
    return found_registry


def get_model_meta_attr(
    attr: str,
    bases: tuple[type, ...],
    meta_class: object | MetaInfo | None = None,
) -> Any | None:
    """Return a `Meta` attribute from the class itself or the nearest parent model.

    This is used while constructing a model class to support inheritance for
    values such as `table_prefix` without hard-coding every inheritable option
    into the metaclass.

    Args:
        attr: Name of the `Meta` attribute to resolve.
        bases: Candidate parent classes to inspect.
        meta_class: Explicit `Meta` object declared on the class being built.

    Returns:
        Any | None: The first non-`None` value found.
    """
    if meta_class is not None:
        direct_attr = getattr(meta_class, attr, None)
        if direct_attr is not None:
            return direct_attr

    for base in bases:
        base_meta: MetaInfo | None = getattr(base, "meta", None)
        if base_meta is None:
            continue
        value = getattr(base_meta, attr, None)
        if value is not None:
            return value
    return None


def _check_manager_for_bases(
    base: type,
    attrs: Any,
    meta: MetaInfo | None = None,
) -> None:
    """Copy inheritable managers from a base class into the new model namespace.

    Manager descriptors live on the class body, so normal Python attribute
    inheritance is not enough when Saffier rebuilds a model namespace during
    metaclass construction. This helper copies manager instances while
    respecting `inherit=False` and the special handling for the default
    `query` manager.

    Args:
        base: Base class currently being inspected.
        attrs: Namespace under construction for the new model.
        meta: Optional metadata object for `base`, used to check abstractness.
    """
    for key, value in inspect.getmembers(base):
        if not isinstance(value, Manager):
            continue

        is_inheritable = bool(getattr(value, "inherit", True))
        if meta and not meta.abstract and not is_inheritable:
            attrs[key] = None
            continue

        # Keep the framework default `query` manager unless a custom manager
        # explicitly opts into overriding inherited `query`.
        inherit_query = bool(getattr(value.__class__, "inherit_query", False))
        if key == "query" and key in attrs and not inherit_query:
            continue

        attrs[key] = copy.copy(value)


def _set_related_name_for_foreign_keys(
    foreign_keys: dict[str, saffier_fields.OneToOneField | saffier_fields.ForeignKey],
    model_class: Union["Model", "ReflectModel"],
) -> set[str]:
    """Resolve and bind reverse relation descriptors for foreign-key-like fields.

    The helper is responsible for generating implicit `related_name` values,
    installing `RelatedField` descriptors on target models, creating placeholder
    fields for reverse lookups, and deferring the work until a string target can
    be resolved from the registry.

    Args:
        foreign_keys: Mapping of local field names to foreign-key-like fields.
        model_class: Model class declaring those fields.

    Returns:
        set[str]: The reverse relation names attached during processing.

    Raises:
        ForeignKeyBadConfigured: If multiple relations would claim the same
            reverse name on the same target model.
    """
    related_names: set[str] = set()
    for name, foreign_key in foreign_keys.items():
        default_related_name = getattr(foreign_key, "related_name", None)

        if default_related_name is False:
            continue

        if not default_related_name:
            if getattr(foreign_key, "unique", False):
                default_related_name = f"{model_class.__name__.lower()}"
            else:
                default_related_name = f"{model_class.__name__.lower()}s_set"

        foreign_key.related_name = default_related_name

        def bind_related_name(
            target_model: type[Any],
            *,
            _default_related_name: str = default_related_name,
            _foreign_key: Any = foreign_key,
            _name: str = name,
        ) -> None:
            existing_related = getattr(target_model, _default_related_name, None)
            if existing_related is not None:
                if (
                    isinstance(existing_related, RelatedField)
                    and existing_related.related_from is model_class
                ):
                    existing_mapping = model_class.meta.related_names_mapping.get(
                        _default_related_name
                    )
                    if existing_mapping not in (None, _name):
                        raise ForeignKeyBadConfigured(
                            f"Multiple related_name with the same value '{_default_related_name}' found to the same target. Related names must be different."
                        )
                    model_class.meta.related_fields[_default_related_name] = existing_related
                    model_class.meta.related_names_mapping[_default_related_name] = _name
                    return
                if not isinstance(existing_related, RelatedField):
                    raise ForeignKeyBadConfigured(
                        f"Multiple related_name with the same value '{_default_related_name}' found to the same target. Related names must be different."
                    )

            related_field = RelatedField(
                related_name=_default_related_name,
                related_to=target_model,
                related_from=model_class,
                embed_parent=getattr(_foreign_key, "embed_parent", None),
            )

            target_models = [target_model]
            proxy_target = target_model.__dict__.get("__proxy_model__")
            if proxy_target is not None and proxy_target not in target_models:
                target_models.append(proxy_target)
            for candidate in target_models:
                setattr(candidate, _default_related_name, related_field)

            model_class.meta.related_fields[_default_related_name] = related_field
            target_meta = cast("MetaInfo", target_model.meta)
            target_meta.related_fields[_default_related_name] = related_field
            if _default_related_name not in target_meta.fields:
                placeholder = saffier_fields.PlaceholderField(
                    name=_default_related_name,
                    no_copy=True,
                    inherit=False,
                )
                placeholder.owner = target_model
                placeholder.registry = target_meta.registry
                target_meta.fields[_default_related_name] = placeholder
                target_meta.fields_mapping[_default_related_name] = placeholder

            model_class.meta.related_names_mapping[_default_related_name] = _name
            target_meta.related_names_mapping[_default_related_name] = _name

            if (
                getattr(_foreign_key, "no_constraint", False)
                and getattr(_foreign_key, "on_delete", None) == saffier.CASCADE
            ) or getattr(_foreign_key, "force_cascade_deletion_relation", False):
                target_model.__require_model_based_deletion__ = True

        registry = getattr(model_class.meta, "registry", None)
        target_model = None
        if isinstance(foreign_key.to, str):
            if registry is not None:
                target_model = registry.models.get(foreign_key.to) or registry.reflected.get(
                    foreign_key.to
                )
                if target_model is None:
                    registry.register_callback(foreign_key.to, bind_related_name, one_time=True)
        else:
            target_model = foreign_key.target

        if target_model is not None:
            bind_related_name(target_model)

        if getattr(foreign_key, "remove_referenced", False):
            model_class.__require_model_based_deletion__ = True

        related_names.add(default_related_name)

    return related_names


def _set_many_to_many_relation(
    m2m: saffier_fields.ManyToManyField,
    model_class: Union["Model", "ReflectModel"],
    field: str,
) -> None:
    """Attach the runtime `Relation` descriptor for a many-to-many field.

    Many-to-many fields are virtual from the model's perspective. Their query
    behavior is exposed through a `Relation` descriptor that knows about the
    target model, the through model, and any deferred string-based references.

    Args:
        m2m: Field being wired.
        model_class: Model class declaring the field.
        field: Attribute name used on `model_class`.
    """
    registry = cast("Registry | None", getattr(model_class.meta, "registry", None))
    relation_name = settings.many_to_many_relation.format(key=field)

    if isinstance(m2m.to, str) and registry is not None:
        target_name = m2m.to
        target_model = registry.models.get(target_name) or registry.reflected.get(target_name)
        if target_model is None:
            setattr(
                model_class,
                relation_name,
                Relation(
                    through=m2m.through,
                    to=target_name,
                    owner=m2m.owner,
                    from_foreign_key=m2m.from_foreign_key,
                    to_foreign_key=m2m.to_foreign_key,
                    embed_through=m2m.embed_through,
                ),
            )

            def finalize_target(resolved_target: type[Any]) -> None:
                m2m.to = resolved_target
                _set_many_to_many_relation(m2m, model_class, field)

            registry.register_callback(target_name, finalize_target, one_time=True)
            return

        m2m.to = target_model

    if isinstance(m2m.through, str) and registry is not None:  # type: ignore
        through_name = m2m.through
        through_model = registry.models.get(through_name) or registry.reflected.get(through_name)
        if through_model is None:
            setattr(
                model_class,
                relation_name,
                Relation(
                    through=through_name,
                    to=m2m.to,
                    owner=m2m.owner,
                    from_foreign_key=m2m.from_foreign_key,
                    to_foreign_key=m2m.to_foreign_key,
                    embed_through=m2m.embed_through,
                ),
            )

            def finalize_relation(resolved_through: type[Any]) -> None:
                m2m.through = resolved_through
                setattr(
                    model_class,
                    relation_name,
                    Relation(
                        through=resolved_through,
                        to=m2m.to,
                        owner=m2m.owner,
                        from_foreign_key=m2m.from_foreign_key,
                        to_foreign_key=m2m.to_foreign_key,
                        embed_through=m2m.embed_through,
                    ),
                )

            registry.register_callback(through_name, finalize_relation, one_time=True)
            return
        m2m.through = through_model

    m2m.create_through_model()
    relation = Relation(
        through=m2m.through,
        to=m2m.to,
        owner=m2m.owner,
        from_foreign_key=m2m.from_foreign_key,
        to_foreign_key=m2m.to_foreign_key,
        embed_through=m2m.embed_through,
    )
    setattr(model_class, relation_name, relation)


def _register_model_signals(model_class: type["Model"]) -> None:
    """Attach the default model lifecycle signals to a class.

    Every concrete model receives a fresh `Broadcaster` instance with the
    standard pre/post save, update, and delete signals.

    Args:
        model_class: Model class receiving the broadcaster.
    """
    signals = Broadcaster()
    signals.pre_save = Signal()
    signals.pre_update = Signal()
    signals.pre_delete = Signal()
    signals.post_save = Signal()
    signals.post_update = Signal()
    signals.post_delete = Signal()
    model_class.meta.signals = signals


def _copy_field(field: Field) -> Field:
    """Copy a field declaration unless it explicitly opts out.

    Args:
        field: Field instance declared on a model.

    Returns:
        Field: Either the original field or a shallow copy, depending on the
        field's `no_copy` flag.
    """
    if getattr(field, "no_copy", False):
        return field
    return copy.copy(field)


class BaseModelMeta(type):
    """Metaclass that turns field declarations into runtime Saffier models.

    `BaseModelMeta` performs almost all of Saffier's ORM construction work. It
    copies inheritable fields and managers, expands composite fields, injects a
    default primary key when appropriate, validates `Meta` options, registers
    the model with its registry, wires reverse relations, and finally generates
    the proxy model used for SQLAlchemy-compatible attribute access.
    """

    __slots__ = ()

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        attrs: Any,
        meta_info_class: type[MetaInfo] = MetaInfo,
        register_content_type: bool = True,
    ) -> Any:
        """Build a Saffier model class from field declarations and inherited metadata.

        The method walks the full inheritance tree, clones fields so model
        definitions do not accidentally share mutable field state, validates the
        effective `Meta` configuration, assigns registries and managers, and
        wires relation descriptors. For concrete models it also creates the
        proxy model and optionally participates in the registry content type
        integration.

        Args:
            name: Name of the model class being created.
            bases: Base classes declared by the model.
            attrs: Class namespace collected from the class body.
            meta_info_class: Metadata container type used for `meta`.
            register_content_type: Whether registry content-type integration
                should run for the new model.

        Returns:
            Any: The newly created model class.

        Raises:
            ImproperlyConfigured: If the model definition is structurally
                invalid, such as missing a usable registry or using an invalid
                manager annotation.
            ValueError: If unsupported `Meta` values or field combinations are
                declared.
        """
        allow_concrete_without_registry = bool(attrs.pop("__skip_registry__", False))
        fields: dict[str, Field] = {}
        one_to_one_fields: set[saffier_fields.OneToOneField] = set()
        foreign_key_fields: dict[
            str, saffier_fields.OneToOneField | saffier_fields.ForeignKey
        ] = {}
        many_to_many_fields: set[saffier_fields.ManyToManyField] = set()
        meta_class: Model.Meta = attrs.get("Meta", type("Meta", (), {}))
        pk_attribute: str = "id"
        registry: Registry | None = None
        declared_manager_names = {
            key for key, value in attrs.items() if isinstance(value, Manager)
        }

        def _to_composite_field(attr_name: str, value: Any) -> Field:
            inner_fields = value
            if hasattr(value, "meta"):
                inner_fields = {
                    field_name: field
                    for field_name, field in value.meta.fields.items()
                    if not getattr(field, "primary_key", False)
                }
            return saffier_fields.CompositeField(
                inner_fields=inner_fields,
                prefix_embedded=f"{attr_name}_",
                model=value,
                owner=value,
            )

        # Searching for fields "Field" in the class hierarchy.
        def __search_for_fields(base: type, inherited_attrs: dict[str, Any]) -> None:
            """
            Search for class attributes of the type fields.Field in the given class.

            If a class attribute is an instance of the Field, then it will be added to the
            field_mapping but only if the key does not exist already.

            If a primary_key field is not provided, it it automatically generate one BigIntegerField for the model.
            """

            for parent in base.__mro__[1:]:
                __search_for_fields(parent, inherited_attrs)

            meta: MetaInfo | None = getattr(base, "meta", None)
            if not meta:
                # Mixins and other classes
                for key, value in inspect.getmembers(base):
                    if isinstance(value, Field) and key not in inherited_attrs:
                        inherited_attrs[key] = value
                    elif isinstance(value, BaseModelMeta) and key not in inherited_attrs:
                        inherited_attrs[key] = _to_composite_field(key, value)

                _check_manager_for_bases(base, inherited_attrs)  # type: ignore[arg-type]
            else:
                # Both abstract and concrete bases respect `inherit=False`.
                for key, value in meta.fields.items():
                    if getattr(value, "inherit", True):
                        inherited_attrs[key] = value
                    else:
                        inherited_attrs.pop(key, None)

                # For managers coming from the top that are not abstract classes
                _check_manager_for_bases(base, inherited_attrs, meta)  # type: ignore[arg-type]

        # Search in the base classes
        for key in list(attrs.keys()):
            value = attrs[key]
            if isinstance(value, BaseModelMeta):
                attrs[key] = _to_composite_field(key, value)

        inherited_fields: dict[str, Any] = {}
        for base in bases:
            __search_for_fields(base, inherited_fields)

        if inherited_fields:
            declared_primary_keys = [
                key
                for key, value in attrs.items()
                if isinstance(value, Field) and value.primary_key
            ]
            if declared_primary_keys and "id" not in declared_primary_keys:
                inherited_id = inherited_fields.get("id")
                if isinstance(inherited_id, Field) and inherited_id.primary_key:
                    inherited_fields.pop("id", None)

            # Making sure the inherited fields are before the new defined.
            attrs = {**inherited_fields, **attrs}

        def _expand_embedded_fields(attrs_map: dict[str, Any]) -> dict[str, Any]:
            if getattr(meta_class, "abstract", False):
                return attrs_map

            extracted_fields = {
                field_name: field
                for field_name, field in attrs_map.items()
                if isinstance(field, Field)
            }
            to_check = deque(extracted_fields.keys())

            while to_check:
                field_name = to_check.pop()
                field = extracted_fields[field_name]
                embedded_fields = field.get_embedded_fields(field_name, extracted_fields)
                if not embedded_fields:
                    continue

                for sub_field_name, sub_field in embedded_fields.items():
                    if sub_field_name == "pk":
                        raise ValueError("sub field uses reserved name pk")
                    sub_field.name = sub_field_name
                    extracted_fields[sub_field_name] = sub_field
                    attrs_map[sub_field_name] = sub_field
                    to_check.appendleft(sub_field_name)

            return attrs_map

        attrs = _expand_embedded_fields(attrs)

        # Handle with multiple primary keys and auto generated field if no primary key is provided
        if name != "Model":
            is_pk_present = False
            for key, value in attrs.items():
                if isinstance(value, Field) and value.primary_key:
                    if not is_pk_present:
                        pk_attribute = key
                    is_pk_present = True

            if (
                not is_pk_present
                and not getattr(meta_class, "abstract", None)
                and not getattr(meta_class, "reflect", None)
            ):
                if "id" not in attrs:
                    attrs = {"id": BigIntegerField(primary_key=True, autoincrement=True), **attrs}

                if not isinstance(attrs["id"], Field) or not attrs["id"].primary_key:
                    raise ImproperlyConfigured(
                        f"Cannot create model {name} without explicit primary key if field 'id' is already present."
                    )

        for key, value in attrs.items():
            if isinstance(value, Field):
                value = _copy_field(value)
                value.name = key

                fields[key] = value

                if isinstance(value, saffier_fields.OneToOneField):
                    one_to_one_fields.add(value)
                    foreign_key_fields[key] = value
                    continue
                elif isinstance(value, saffier_fields.ManyToManyField):
                    many_to_many_fields.add(value)
                    continue
                elif (
                    isinstance(value, saffier_fields.ForeignKey)
                    and not getattr(value, "is_model_reference", False)
                    and not isinstance(
                        value,
                        saffier_fields.ManyToManyField,  # type: ignore
                    )
                ):
                    foreign_key_fields[key] = value
                    continue

        for slot in fields:
            attrs.pop(slot, None)
        attrs["meta"] = meta = meta_info_class(meta_class)

        meta.fields = fields
        meta.fields_mapping = fields
        meta.foreign_key_fields = foreign_key_fields
        meta.one_to_one_fields = one_to_one_fields
        meta.many_to_many_fields = many_to_many_fields
        meta.pk_attribute = pk_attribute
        meta.pk = fields.get(pk_attribute)
        meta.special_getter_fields = {
            field_name
            for field_name, field in fields.items()
            if getattr(field, "is_computed", False)
        }
        meta.secret_fields = {
            field_name for field_name, field in fields.items() if getattr(field, "secret", False)
        }
        meta._needs_special_serialization = None

        if not fields:
            meta.abstract = True

        model_class = super().__new__

        # Ensure the initialization is only performed for subclasses of Model
        parents = [parent for parent in bases if isinstance(parent, BaseModelMeta)]
        if not parents:
            return model_class(cls, name, bases, attrs)

        meta.parents = parents
        new_class = cast("type[Model]", model_class(cls, name, bases, attrs))
        new_class._db_schemas = {}

        manager_annotations = inspect.get_annotations(new_class, eval_str=True)
        for manager_name in declared_manager_names:
            manager_annotation = manager_annotations.get(manager_name)
            if manager_annotation is ClassVar or get_origin(manager_annotation) is ClassVar:
                continue
            raise ImproperlyConfigured(
                f"Managers must be ClassVar type annotated and '{manager_name}' is not or not correctly annotated."
            )

        plain_model_fields: dict[str, dict[str, Any]] = {}
        for base in bases:
            plain_model_fields.update(copy.deepcopy(getattr(base, "__plain_model_fields__", {})))

        model_fields: dict[str, Any] = {**plain_model_fields, **fields}
        for field_name, annotation in manager_annotations.items():
            if field_name in fields or field_name.startswith("_"):
                continue
            if field_name in declared_manager_names:
                continue
            if get_origin(annotation) is ClassVar:
                continue
            plain_model_fields[field_name] = {
                "annotation": annotation,
                "default": getattr(new_class, field_name, None),
            }
            model_fields[field_name] = plain_model_fields[field_name]

        new_class.__plain_model_fields__ = plain_model_fields
        new_class.model_fields = model_fields

        if not meta.abstract:
            meta.init_field_stats()

        # Validate meta collection types before inheriting from bases.
        for attr_name in ("unique_together", "indexes", "constraints"):
            attr_value = getattr(meta, attr_name, None)
            if attr_value is not None and not isinstance(attr_value, (list, tuple)):
                value_type = type(attr_value).__name__
                raise ImproperlyConfigured(
                    f"{attr_name} must be a tuple or list. Got {value_type} instead."
                )

        meta.unique_together = list(meta.unique_together or [])
        meta.indexes = list(meta.indexes or [])
        meta.constraints = list(meta.constraints or [])

        # Inherit parent meta options where the child didn't explicitly define them.
        for base in new_class.__bases__:
            if not hasattr(base, "meta"):
                continue

            base_meta = cast("MetaInfo", base.meta)
            if base_meta.unique_together:
                meta.unique_together = [*base_meta.unique_together, *meta.unique_together]
            if base_meta.indexes:
                meta.indexes = [*base_meta.indexes, *meta.indexes]
            if base_meta.constraints:
                meta.constraints = [*base_meta.constraints, *meta.constraints]

        meta.table_prefix = cast(
            "str | None",
            get_model_meta_attr("table_prefix", bases, meta_class),
        )

        # Abstract classes do not allow multiple managers. This make sure it is enforced.
        if meta.abstract:
            base_managers = [
                key
                for key, value in attrs.items()
                if isinstance(value, Manager) and not isinstance(value, RedirectManager)
            ]
            if len(base_managers) > 1:
                raise ImproperlyConfigured(
                    "Multiple managers are not allowed in abstract classes."
                )
        else:
            meta.managers = [k for k, v in attrs.items() if isinstance(v, Manager)]

        # Handle the registry of models
        skip_registry_lookup = getattr(meta_class, "registry", None) is False
        if skip_registry_lookup and not meta.abstract and not allow_concrete_without_registry:
            raise ImproperlyConfigured(
                "Meta.registry = False can only be used on abstract models."
            )

        if getattr(meta, "registry", None) is None and not skip_registry_lookup:
            if meta.abstract:
                new_class.__db_model__ = True
                new_class.fields = meta.fields
                meta.model = new_class
                meta.manager.model_class = new_class
                for _, value in new_class.fields.items():
                    value.owner = new_class
                for manager_name, value in attrs.items():
                    if isinstance(value, Manager):
                        value.name = manager_name
                        value.model_class = new_class
                return new_class
            if hasattr(new_class, "__db_model__") and new_class.__db_model__:
                meta.registry = _check_model_inherited_registry(bases)
            else:
                return new_class

        # Making sure the tablename is always set if the value is not provided
        if getattr(meta, "tablename", None) is None:
            tablename = f"{name.lower()}s"
            if meta.table_prefix:
                tablename = f"{meta.table_prefix}_{tablename}"
            meta.tablename = tablename

        # Handle unique together
        if meta.unique_together:
            for value in meta.unique_together:
                if not isinstance(value, (str, tuple, UniqueConstraint)):
                    raise ValueError(
                        "The values inside the unique_together must be a string, a tuple of strings or an instance of UniqueConstraint."
                    )

        # Handle indexes
        if meta.indexes:
            for value in meta.indexes:
                if not isinstance(value, Index):
                    raise ValueError("Meta.indexes must be a list of Index types.")

        # Handle constraints
        if meta.constraints:
            for value in meta.constraints:
                if not isinstance(value, sqlalchemy.Constraint):
                    raise ValueError(
                        "Meta.constraints must be a list of sqlalchemy.Constraint types."
                    )

        if skip_registry_lookup:
            new_class.__db_model__ = True
            new_class.fields = meta.fields
            meta.model = new_class
            meta.manager.model_class = new_class
            for _, value in new_class.fields.items():
                value.owner = new_class
            return new_class

        registry = meta.registry
        new_class.database = registry.database  # type: ignore[union-attr]

        # Making sure it does not generate tables if abstract it set
        if not meta.abstract:
            registry.models[name] = new_class  # type: ignore[union-attr]

        for field_name, field in meta.fields.items():
            field.registry = registry
            if field.primary_key and field_name == meta.pk_attribute:
                new_class.pkname = field_name

        new_class.__db_model__ = True
        new_class.fields = meta.fields
        meta.model = new_class
        meta.manager.model_class = new_class

        # Set the owner of the field
        for _, value in new_class.fields.items():
            value.owner = new_class

        # Sets the foreign key fields
        if meta.foreign_key_fields and not new_class.is_proxy_model:
            related_names = _set_related_name_for_foreign_keys(meta.foreign_key_fields, new_class)
            meta.related_names.update(related_names)

        for field, value in list(new_class.fields.items()):  # type: ignore
            if isinstance(value, saffier_fields.ManyToManyField):
                _set_many_to_many_relation(value, new_class, field)

        # Set the manager
        for manager_name, value in attrs.items():
            if isinstance(value, Manager):
                value.name = manager_name
                value.model_class = new_class

        # Register the signals
        _register_model_signals(new_class)

        # Update the model references with the validations of the model
        # Being handled by the Saffier fields instead.
        # Generates a proxy model for each model created
        # Making sure the core model where the fields are inherited
        # And mapped contains the main proxy_model
        if not new_class.is_proxy_model and not new_class.meta.abstract:
            proxy_model = new_class.generate_proxy_model()
            new_class.__proxy_model__ = proxy_model
            new_class.__proxy_model__.parent = new_class
            meta.registry.models[new_class.__name__] = new_class  # type: ignore

        if (
            register_content_type
            and registry is not None
            and not new_class.meta.abstract
            and not new_class.is_proxy_model
            and hasattr(registry, "_handle_model_registration")
        ):
            registry._handle_model_registration(new_class)
        if registry is not None and hasattr(registry, "execute_model_callbacks"):
            registry.execute_model_callbacks(new_class)

        return new_class

    def get_db_schema(cls) -> str | None:
        """Return the default registry schema associated with the model.

        Returns:
            str | None: Registry-level default schema, or `None` when the model
            is detached from a registry.
        """
        meta = getattr(cls, "meta", None)
        if meta is None or getattr(meta, "registry", None) is None:
            return None
        return cast("str | None", meta.registry.db_schema)

    def get_db_shema(cls) -> str | None:
        """Backward-compatible misspelled alias for `get_db_schema()`.

        Returns:
            str | None: Same value returned by `get_db_schema()`.
        """
        return cls.get_db_schema()

    @property
    def table(cls) -> Any:
        """Return the model table for the active default schema.

        Proxy models delegate to their parent model, while concrete models lazily
        build and cache the SQLAlchemy table for the registry default schema.

        Returns:
            Any: SQLAlchemy table object bound to the default schema.

        Raises:
            AttributeError: If the model has no registry or an invalid proxy
                parent.
        """
        if getattr(cls, "is_proxy_model", False):
            parent = getattr(cls, "parent", None)
            if parent is None:
                raise AttributeError("No parent model found for proxy model.")
            return parent.table
        if getattr(cls.meta, "registry", None) is None:
            raise AttributeError("No registry.")

        db_schema = cls.get_db_schema()

        if not hasattr(cls, "_table") or cls._table is None:
            cls._table = cls.build(db_schema)
        elif hasattr(cls, "_table"):
            table = cls._table
            if table.name.lower() != cls.meta.tablename:
                cls._table = cls.build(db_schema)
        return cls._table

    def __getattr__(cls, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)

        meta = cls.__dict__.get("meta")
        if (
            meta is not None
            and meta.model is cls
            and not meta.abstract
            and _is_sqlalchemy_compatibility_enabled(cls)
        ):
            resolver = type.__getattribute__(cls, "_resolve_sqlalchemy_compatible_attribute")
            try:
                return resolver(name)
            except AttributeError:
                pass
        raise AttributeError(name)

    @table.setter
    def table(self, value: sqlalchemy.Table) -> None:
        self._table = value

    def table_schema(
        cls,
        schema: str | None = None,
        *,
        metadata: sqlalchemy.MetaData | None = None,
        update_cache: bool = False,
    ) -> Any:
        """Return the model table bound to a specific schema.

        Saffier caches one SQLAlchemy `Table` per schema so tenant-specific or
        manually selected schemas do not mutate the shared registry metadata. If
        the requested schema matches the registry default schema, the shared
        table cache is used. Otherwise a per-schema table is built and cached in
        `_db_schemas`.

        Args:
            schema: Schema name to bind the table to.
            metadata: Accepted for compatibility with related APIs but ignored.
            update_cache: When `True`, force rebuilding the cached table.

        Returns:
            Any: The SQLAlchemy table object for the requested schema.
        """
        del metadata  # metadata is accepted for API parity with Edgy.
        if getattr(cls, "is_proxy_model", False):
            parent = getattr(cls, "parent", None)
            if parent is None:
                raise AttributeError("No parent model found for proxy model.")
            return parent.table_schema(schema=schema, update_cache=update_cache)

        table = getattr(cls, "_table", None)
        if (
            not update_cache
            and table is not None
            and table.name.lower() == cls.meta.tablename
            and getattr(table, "schema", None) == schema
        ):
            return table

        if schema is None or (cls.get_db_schema() or "") == schema:
            if update_cache or table is None or table.name.lower() != cls.meta.tablename:
                cls._table = cls.build(schema=schema)
            return cls.table

        schema_obj = cls._db_schemas.pop(schema, None)
        if schema_obj is None or update_cache:
            schema_obj = cls.build(schema=schema)
        cls._db_schemas[schema] = schema_obj
        while len(cls._db_schemas) > 100:
            cls._db_schemas.pop(next(iter(cls._db_schemas)), None)

        return schema_obj

    @property
    def pknames(cls) -> Sequence[str]:
        """Return the logical field names that compose the primary key.

        Returns:
            Sequence[str]: One or more Saffier field names forming the PK.
        """
        cached = cls.__dict__.get("_pknames")
        if cached is None:
            names = tuple(
                field_name
                for field_name, field in cls.fields.items()
                if getattr(field, "primary_key", False)
            )
            if not names:
                names = (getattr(cls, "pkname", "id"),)
            cls._pknames = names
        return cast("Sequence[str]", cls._pknames)

    @property
    def pkcolumns(cls) -> Sequence[str]:
        """Return the physical column names that compose the primary key.

        Returns:
            Sequence[str]: Database column names used by the model primary key.
        """
        cached = cls.__dict__.get("_pkcolumns")
        if cached is None:
            try:
                names = tuple(column.key for column in cls.table.primary_key.columns)
            except Exception:
                names = ()
            if not names:
                names = tuple(cls.pknames)
            cls._pkcolumns = names
        return cast("Sequence[str]", cls._pkcolumns)

    @property
    def signals(cls) -> "Broadcaster":
        """Return the lifecycle signal broadcaster attached to the model class.

        Returns:
            Broadcaster: Signal broadcaster configured for the model.
        """
        return cast("Broadcaster", cls.meta.signals)

    def transaction(cls, *, force_rollback: bool = False, **kwargs: Any) -> Any:
        return cls.database.transaction(force_rollback=force_rollback, **kwargs)

    @property
    def proxy_model(cls) -> Any:
        """Return the lazily generated proxy model for SQLAlchemy-style access.

        Returns:
            Any: Proxy model class corresponding to the concrete model.
        """
        if getattr(cls, "is_proxy_model", False):
            return cls
        if cls.__dict__.get("__proxy_model__") is None:
            proxy_model = cls.generate_proxy_model()
            proxy_model.parent = cls
            cls.__proxy_model__ = proxy_model
        return cls.__proxy_model__

    @property
    def columns(cls) -> sqlalchemy.sql.ColumnCollection:
        return cast("sqlalchemy.sql.ColumnCollection", cls.table.columns)


class BaseModelReflectMeta(BaseModelMeta):
    """Variant of `BaseModelMeta` that registers models as reflected models.

    Reflected models go through the same field and manager setup as concrete
    models, but they are removed from the registry's `models` mapping and stored
    in `registry.reflected` instead so migration and reflection code can treat
    them differently.
    """

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        attrs: Any,
        **kwargs: Any,
    ) -> Any:
        new_model = super().__new__(
            cls,
            name,
            bases,
            attrs,
            register_content_type=False,
            **kwargs,
        )

        registry = new_model.meta.registry

        # Remove the reflected models from the registry
        # Add the reflecte model to the views section of the refected
        if registry:
            try:
                registry.models.pop(new_model.__name__)
                registry.reflected[new_model.__name__] = new_model
            except KeyError:
                ...

        return new_model


class ModelMeta(metaclass=BaseModelMeta):
    """Marker metaclass used by standard concrete Saffier models.

    The class exists so user models can inherit a stable metaclass symbol while
    the real implementation lives in `BaseModelMeta`.
    """


class ReflectMeta(metaclass=BaseModelReflectMeta):
    """Marker metaclass used by reflected Saffier models.

    This mirrors `ModelMeta` but routes construction through
    `BaseModelReflectMeta`, which stores models in the registry's reflected-model
    mapping.
    """
