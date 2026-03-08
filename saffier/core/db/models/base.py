"""Base model classes shared by concrete and reflected Saffier models."""

import copy
import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast, get_args, get_origin

import sqlalchemy
from sqlalchemy.engine import Engine
from typing_extensions import Self

import saffier
from saffier.conf import settings
from saffier.core.db.context_vars import (
    CURRENT_FIELD_CONTEXT,
    CURRENT_INSTANCE,
    CURRENT_MODEL_INSTANCE,
    CURRENT_PHASE,
)
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.models.managers import Manager, RedirectManager
from saffier.core.db.models.metaclasses import (
    BaseModelMeta,
    BaseModelReflectMeta,
    MetaInfo,
    _register_model_signals,
    _set_many_to_many_relation,
    _set_related_name_for_foreign_keys,
)
from saffier.core.db.models.model_proxy import ProxyModel
from saffier.core.utils.models import DateParser, create_saffier_model, generify_model_fields
from saffier.engines.base import EngineIncludeExclude, resolve_model_engine
from saffier.exceptions import ImproperlyConfigured, ValidationError

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.signals import Broadcaster
    from saffier.engines.base import ModelEngine

saffier_setattr = object.__setattr__

_MODEL_COPY_EXCLUDED_ATTRS = {
    "fields",
    "meta",
    "_table",
    "_db_schemas",
    "__proxy_model__",
    "_pknames",
    "_pkcolumns",
}


class SaffierBaseModel(DateParser, metaclass=BaseModelMeta):
    """Common model behavior shared by concrete and reflected models.

    The base model contains the ORM logic that is independent from the actual
    insert/update/delete implementation. It normalizes constructor payloads,
    tracks identifying fields, supports schema-aware table selection, stages
    reverse relation writes, persists model references, and exposes the cloning
    helpers used by registry-copy and proxy-model generation.
    """

    is_proxy_model: ClassVar[bool] = False
    query: ClassVar[Manager] = Manager()
    query_related: ClassVar[Manager] = RedirectManager(redirect_name="query")
    meta: ClassVar[MetaInfo] = MetaInfo(None)
    __db_model__: ClassVar[bool] = False
    __raw_query__: ClassVar[str | None] = None
    __proxy_model__: ClassVar[type["Model"] | None] = None
    __no_load_trigger_attrs__: ClassVar[set[str]] = set()
    __using_schema__: ClassVar[str | None] = None
    __require_model_based_deletion__: ClassVar[bool] = False
    __deletion_with_signals__: ClassVar[bool] = False
    __skip_generic_reverse_delete__: ClassVar[bool] = False

    def __init__(self, *model_refs: Any, **kwargs: Any) -> None:
        self.__dict__["__no_load_trigger_attrs__"] = set(
            getattr(self.__class__, "__no_load_trigger_attrs__", set())
        )
        self.__dict__["_db_deleted"] = False
        self.__dict__["transaction"] = functools.partial(self._instance_transaction)
        self.setup_model_fields_from_kwargs(model_refs, kwargs)

    @staticmethod
    def _is_model_ref_instance(value: Any) -> bool:
        return (
            hasattr(value, "model_dump")
            and hasattr(value.__class__, "__model_ref_fields__")
            and hasattr(value.__class__, "__related_name__")
        )

    @classmethod
    def resolve_model_ref_field_name(cls, ref_type: type[Any]) -> str:
        """Return the `RefForeignKey` field that accepts `ref_type` references.

        Args:
            ref_type: Concrete `ModelRef` subclass being supplied positionally.

        Returns:
            str: Name of the field that can store references of this type.

        Raises:
            ModelReferenceError: If no `RefForeignKey` on the model accepts the
                provided reference type.
        """
        for field_name, field in cls.fields.items():
            model_ref = getattr(field, "model_ref", None)
            if model_ref is not None and issubclass(ref_type, model_ref):
                return field_name
        raise saffier.ModelReferenceError(
            detail=(
                f"No RefForeignKey on '{cls.__name__}' accepts model references of type "
                f"'{ref_type.__name__}'."
            )
        )

    @classmethod
    def merge_model_refs(
        cls,
        model_refs: Sequence[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge positional `ModelRef` objects into a keyword payload.

        Saffier reserves positional constructor arguments for model reference
        objects so callers can write `Article(tag_ref, author_ref, title="...")`
        and still end up with a normal keyword payload keyed by the owning
        `RefForeignKey` fields.

        Args:
            model_refs: Positional constructor arguments.
            kwargs: Existing keyword payload.

        Returns:
            dict[str, Any]: Normalized keyword payload including merged model
            references.

        Raises:
            TypeError: If any positional argument is not a model reference
                instance.
        """
        payload = dict(kwargs or {})
        if not model_refs:
            return payload

        for model_ref in model_refs:
            if not cls._is_model_ref_instance(model_ref):
                raise TypeError("Positional arguments are reserved for ModelRef instances.")

            field_name = cls.resolve_model_ref_field_name(model_ref.__class__)
            existing = payload.get(field_name)
            if existing is None:
                payload[field_name] = [model_ref]
            elif isinstance(existing, Sequence) and not isinstance(
                existing, (str, bytes, bytearray)
            ):
                payload[field_name] = [*existing, model_ref]
            else:
                payload[field_name] = [existing, model_ref]
        return payload

    def setup_model_fields_from_kwargs(
        self,
        model_refs: Sequence[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        """Normalize constructor input and assign values onto the instance.

        Positional `ModelRef` arguments are merged into the keyword payload,
        composite or virtual inputs are expanded through field hooks, and each
        resulting value is assigned using normal model attribute semantics so
        relation-aware setters still run.

        Args:
            model_refs: Positional model-reference objects.
            kwargs: Raw keyword payload supplied to the constructor.

        Returns:
            Any: Normalized payload after assignment.

        Raises:
            ValueError: If the payload contains unknown public attributes.
        """
        kwargs = self.__class__.merge_model_refs(model_refs, kwargs)
        kwargs = self.__class__.normalize_field_kwargs(kwargs)

        if "pk" in kwargs:
            self.pk = kwargs.pop("pk")

        for key, value in kwargs.items():
            if key not in self.fields and not hasattr(self, key):
                raise ValueError(f"Invalid keyword {key} for class {self.__class__.__name__}")

            if key in self.get_plain_model_fields():
                value = self.validate_plain_field_value(key, value)

            # Set model field and add to the kwargs dict
            setattr(self, key, value)
            kwargs[key] = value
        return kwargs

    @classmethod
    def get_plain_model_fields(cls) -> dict[str, dict[str, Any]]:
        return cast("dict[str, dict[str, Any]]", getattr(cls, "__plain_model_fields__", {}))

    @classmethod
    def _matches_plain_annotation(cls, annotation: Any, value: Any) -> bool:
        del cls
        if annotation in (Any, None):
            return True

        origin = get_origin(annotation)
        if origin is None:
            if annotation is type(None):
                return value is None
            if isinstance(annotation, type):
                if annotation is int and isinstance(value, bool):
                    return False
                return isinstance(value, annotation)
            return True

        if str(origin) in {"typing.Union", "types.UnionType"}:
            return any(
                SaffierBaseModel._matches_plain_annotation(arg, value)
                for arg in get_args(annotation)
            )

        if origin in (list, set, tuple, dict):
            return isinstance(value, origin)

        if origin in (Sequence,):
            return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))

        if isinstance(origin, type):
            return isinstance(value, origin)
        return True

    @classmethod
    def validate_plain_field_value(cls, key: str, value: Any) -> Any:
        plain_field = cls.get_plain_model_fields().get(key)
        if plain_field is None:
            return value
        annotation = plain_field.get("annotation")
        if cls._matches_plain_annotation(annotation, value):
            return value
        raise ValidationError(text=f"Invalid value for '{key}'.", code="type")

    @classmethod
    def normalize_field_kwargs(cls, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Normalize constructor or persistence payloads through field hooks.

        Every field may rewrite or expand incoming values before validation. This
        is how composite fields, foreign keys, and other virtual helpers expose a
        convenient high-level API while still producing a concrete payload.

        Args:
            kwargs: Input payload keyed by logical field name.

        Returns:
            dict[str, Any]: Normalized payload.
        """
        payload = dict(kwargs or {})
        for field_name, field in cls.fields.items():
            field.modify_input(field_name, payload)
        return payload

    @classmethod
    def get_model_engine_name(cls) -> str | None:
        configured = getattr(cls.meta, "model_engine", None)
        if configured is False:
            return None
        if configured is None:
            configured = getattr(getattr(cls.meta, "registry", None), "model_engine", None)
        if configured in (None, False):
            return None
        if isinstance(configured, str):
            return configured
        return cast("str", getattr(configured, "name", None))

    @classmethod
    def get_model_engine(cls) -> "ModelEngine | None":
        configured = getattr(cls.meta, "model_engine", None)
        if configured is False:
            return None
        if configured is None:
            configured = getattr(getattr(cls.meta, "registry", None), "model_engine", None)
        return resolve_model_engine(configured)

    @classmethod
    def require_model_engine(cls) -> "ModelEngine":
        engine = cls.get_model_engine()
        if engine is None:
            raise ImproperlyConfigured(f"Model '{cls.__name__}' has no model engine configured.")
        return engine

    @classmethod
    def get_engine_model_class(cls, *, mode: str = "projection") -> type[Any]:
        return cls.require_model_engine().get_model_class(cls, mode=mode)

    @classmethod
    def engine_validate(cls, value: Any, *, mode: str = "validation") -> Any:
        return cls.require_model_engine().validate_model(cls, value, mode=mode)

    @classmethod
    def from_engine(cls, value: Any, *, exclude_unset: bool = True) -> "Self":
        payload = cls.require_model_engine().to_saffier_data(
            cls,
            value,
            exclude_unset=exclude_unset,
        )
        return cls(**payload)

    @classmethod
    def engine_json_schema(cls, *, mode: str = "projection", **kwargs: Any) -> dict[str, Any]:
        return cls.require_model_engine().json_schema(cls, mode=mode, **kwargs)

    def to_engine_model(
        self,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> Any:
        return (
            type(self)
            .require_model_engine()
            .project_model(
                self,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
            )
        )

    def engine_dump(
        self,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        return (
            type(self)
            .require_model_engine()
            .dump_model(
                self,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
            )
        )

    def engine_dump_json(
        self,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> str:
        return (
            type(self)
            .require_model_engine()
            .dump_model_json(
                self,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
            )
        )

    async def _persist_model_references(self, field_names: set[str] | None = None) -> None:
        """Persist staged `RefForeignKey` values after a successful save.

        Args:
            field_names: Optional subset of reference fields to persist.
        """
        for field_name, field in self.fields.items():
            if not getattr(field, "is_model_reference", False):
                continue
            if field_names is not None and field_name not in field_names:
                continue
            if field_name not in self.__dict__:
                continue
            await field.persist_references(self, self.__dict__[field_name])

    async def _persist_related_fields(self, field_names: set[str] | None = None) -> None:
        """Persist staged reverse-relation values after the model is saved.

        Args:
            field_names: Optional subset of reverse relation names to flush.
        """
        for field_name in self.meta.related_fields:
            if field_names is not None and field_name not in field_names:
                continue
            if field_name not in self.__dict__:
                continue
            value = self.__dict__[field_name]
            save_related = getattr(value, "save_related", None)
            if callable(save_related):
                await save_related()

    @staticmethod
    def _normalize_identifier_value(value: Any) -> Any:
        if hasattr(value, "__db_model__"):
            return getattr(value, "pk", None)
        return value

    def _pk_values(self) -> dict[str, Any]:
        return {
            field_name: self._normalize_identifier_value(getattr(self, field_name, None))
            for field_name in type(self).pknames
        }

    def _instance_transaction(self, *, force_rollback: bool = False, **kwargs: Any) -> Any:
        return self.database.transaction(force_rollback=force_rollback, **kwargs)

    @property
    def pk(self) -> Any:
        """Return the model primary key in scalar or mapping form.

        Single-column primary keys are returned as the raw value. Composite
        primary keys are returned as a mapping from logical field name to value,
        unless every component is `None`, in which case `None` is returned.
        """
        values = self._pk_values()
        if len(values) == 1:
            return next(iter(values.values()))
        if values and all(value is None for value in values.values()):
            return None
        return values

    @pk.setter
    def pk(self, value: Any) -> Any:
        if len(type(self).pknames) == 1:
            if isinstance(value, dict):
                value = value.get(self.pkname)
            setattr(self, self.pkname, value)
            return

        if value is None:
            payload = dict.fromkeys(type(self).pknames)
        elif hasattr(value, "__db_model__"):
            payload = getattr(value, "pk", None) or {}
        else:
            payload = value

        if not isinstance(payload, dict):
            raise ValueError(
                f"Composite primary keys on '{self.__class__.__name__}' require a mapping value."
            )

        for field_name in type(self).pknames:
            setattr(self, field_name, payload.get(field_name))

    @property
    def raw_query(self) -> Any:
        return getattr(self, self.__raw_query__)  # type: ignore

    @raw_query.setter
    def raw_query(self, value: Any) -> Any:
        setattr(self, self.raw_query, value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def join_identifiers_to_string(self, *, sep: str = ", ", sep_inner: str = "=") -> str:
        pairs = [
            f"{field_name}{sep_inner}{self._normalize_identifier_value(getattr(self, field_name, None))}"
            for field_name in self.identifying_db_fields
        ]
        return sep.join(pairs)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.join_identifiers_to_string()})"

    @property
    def table(self) -> sqlalchemy.Table:
        if getattr(self, "_table", None) is None:
            schema = self.get_active_instance_schema()
            if schema is not None:
                return cast("sqlalchemy.Table", self.__class__.table_schema(schema))
            return cast("sqlalchemy.Table", self.__class__.table)
        return self._table

    @table.setter
    def table(self, value: sqlalchemy.Table) -> None:
        self._table = value

    @functools.cached_property
    def proxy_model(self) -> Any:
        return self.__class__.proxy_model

    @functools.cached_property
    def signals(self) -> "Broadcaster":
        return self.__class__.signals  # type: ignore

    @classmethod
    def get_real_class(cls) -> type["Model"]:
        if getattr(cls, "is_proxy_model", False):
            return cast("type[Model]", cls.parent)
        return cast("type[Model]", cls)

    @functools.cached_property
    def identifying_db_fields(self) -> Sequence[str]:
        """
        Returns the database columns that uniquely identify the current instance.

        Saffier currently uses the model primary key columns for this.
        """
        pkcolumns = getattr(self.__class__, "pkcolumns", ())
        return tuple(pkcolumns) or (self.pkname,)

    @property
    def can_load(self) -> bool:
        """Return whether the instance can be reloaded from the database.

        The instance must belong to a concrete registered model and expose all
        identifying database fields.
        """
        return bool(
            self.meta.registry
            and not self.meta.abstract
            and all(
                getattr(self, field_name, None) is not None
                for field_name in self.identifying_db_fields
            )
        )

    def create_model_key(self) -> tuple[Any, ...]:
        """Create a stable identity tuple for recursion guards.

        Returns:
            tuple[Any, ...]: Tuple containing the model class and identifying
            values.
        """
        return (
            self.__class__,
            *(
                self._normalize_identifier_value(getattr(self, field_name, None))
                for field_name in self.identifying_db_fields
            ),
        )

    def identifying_clauses(
        self,
        *,
        table: sqlalchemy.Table | None = None,
        fields: Sequence[str] | None = None,
    ) -> list[Any]:
        """Build equality clauses that uniquely identify the current instance.

        Args:
            table: Optional table object to target instead of the active instance
                table.
            fields: Optional subset of identifying fields to include.

        Returns:
            list[Any]: SQLAlchemy boolean expressions suitable for `WHERE`.
        """
        active_table = table or self.table
        clauses = []
        for field_name in tuple(fields or self.identifying_db_fields):
            column = getattr(active_table.c, field_name, None)
            if column is None:
                continue
            clauses.append(
                column == self._normalize_identifier_value(getattr(self, field_name, None))
            )
        return clauses

    def _has_loaded_db_fields(self) -> bool:
        return all(
            field_name in self.__dict__
            for field_name, field in self.fields.items()
            if field.has_column()
        )

    @classmethod
    def get_active_class_schema(cls) -> str | None:
        """Return the schema pinned directly on the model class.

        Returns:
            str | None: Class-level schema override, if present.
        """
        return cast("str | None", getattr(cls, "__using_schema__", None))

    def get_active_instance_schema(self) -> str | None:
        """Return the schema currently active for this instance.

        Instance-level overrides win over cached table schema, which in turn wins
        over the class-level override.

        Returns:
            str | None: Active schema for this instance.
        """
        explicit = self.__dict__.get("__using_schema__", None)
        if explicit is not None:
            return cast("str | None", explicit)
        table = self.__dict__.get("_table", None)
        if table is not None:
            return cast("str | None", getattr(table, "schema", None))
        return self.__class__.get_active_class_schema()

    async def load_recursive(
        self,
        only_needed: bool = False,
        only_needed_nest: bool = False,
        _seen: set[tuple[Any, ...]] | None = None,
    ) -> None:
        """Load the instance and recurse through already-linked FK relations.

        The method is careful to avoid infinite loops by tracking visited model
        identities while traversing the object graph.

        Args:
            only_needed: Whether to skip reloading when DB-backed fields are
                already populated.
            only_needed_nest: Whether nested relations should stop after the
                current object was already fully loaded.
            _seen: Internal recursion guard keyed by model identity.
        """
        model_key = self.create_model_key()
        if _seen is None:
            _seen = {model_key}
        elif model_key in _seen:
            return
        else:
            _seen.add(model_key)

        was_loaded = self._has_loaded_db_fields()
        if self.can_load:
            await self.load(only_needed=only_needed)

        if only_needed_nest and was_loaded:
            return

        for field_name in self.meta.foreign_key_fields:
            value = getattr(self, field_name, None)
            if value is not None and hasattr(value, "load_recursive"):
                await value.load_recursive(
                    only_needed=only_needed,
                    only_needed_nest=True,
                    _seen=_seen,
                )

    def get_instance_name(self) -> str:
        """Return the lowercase class name used by relation helpers.

        Returns:
            str: Lowercase model class name.
        """
        return self.__class__.__name__.lower()

    @classmethod
    def _copy_model_definitions(
        cls,
        *,
        registry: "saffier.Registry | None" = None,
        unlink_same_registry: bool = True,
    ) -> dict[str, Any]:
        """Copy fields and managers for dynamic model cloning.

        Relation fields may be rewritten as string references when the target
        registry is still under construction so copied models do not retain live
        references back into the source registry.

        Args:
            registry: Optional destination registry receiving the copy.
            unlink_same_registry: Whether relations inside the same source
                registry should be rewritten as string references.

        Returns:
            dict[str, Any]: Definitions suitable for dynamic model creation.
        """
        from saffier.core.db.fields.base import ForeignKey, ManyToManyField

        definitions: dict[str, Any] = {}
        source_registry = getattr(cls.meta, "registry", None)
        existing_annotations = dict(getattr(cls, "__annotations__", {}))
        manager_annotations: dict[str, Any] = {}

        for field_name, field in cls.fields.items():
            if getattr(field, "no_copy", False):
                continue
            field_copy = copy.copy(field)
            if hasattr(field_copy, "_target"):
                delattr(field_copy, "_target")

            if source_registry not in (None, False):
                if isinstance(field_copy, ForeignKey):
                    target = field.target
                    if getattr(target.meta, "registry", None) is source_registry:
                        if unlink_same_registry:
                            field_copy.to = target.__name__
                        elif registry is not None:
                            field_copy.related_name = False
                elif isinstance(field_copy, ManyToManyField):
                    target = field.target
                    if (
                        getattr(target.meta, "registry", None) is source_registry
                        and unlink_same_registry
                    ):
                        field_copy.to = target.__name__
                    through = getattr(field_copy, "through", None)
                    if (
                        isinstance(through, type)
                        and getattr(through.meta, "registry", None) is source_registry
                        and unlink_same_registry
                    ):
                        field_copy.through = through.__name__

            definitions[field_name] = field_copy

        for manager_name in getattr(cls.meta, "managers", []):
            manager = getattr(cls, manager_name, None)
            if isinstance(manager, Manager):
                definitions[manager_name] = copy.copy(manager)
                manager_annotations[manager_name] = existing_annotations.get(
                    manager_name,
                    ClassVar[Any],
                )

        if manager_annotations:
            definitions["__annotations__"] = {
                **existing_annotations,
                **manager_annotations,
            }

        return definitions

    @classmethod
    def copy_saffier_model(
        cls,
        registry: "saffier.Registry | None" = None,
        name: str = "",
        unlink_same_registry: bool = True,
        on_conflict: str = "error",
    ) -> type["Model"]:
        """Create a detached copy of the model class with copied field state.

        The copy is used by migration preparation, proxy generation, and tests
        that need to attach the same logical model definition to another
        registry. Field instances are copied so later mutations on the copied
        model do not leak back into the original model definition.

        Args:
            registry: Optional registry to immediately attach the copied model
                to.
            name: Optional replacement class name.
            unlink_same_registry: Whether same-registry relations should be
                rewritten as string references during the copy.
            on_conflict: Conflict strategy used if `registry` already contains a
                model with the target name.

        Returns:
            type[Model]: The detached or newly attached copied model class.
        """
        existing_annotations = dict(getattr(cls, "__annotations__", {}))
        definitions = {
            key: value
            for key, value in cls.__dict__.items()
            if key not in _MODEL_COPY_EXCLUDED_ATTRS and not key.startswith("__")
        }
        definitions.update(
            cls._copy_model_definitions(
                registry=registry, unlink_same_registry=unlink_same_registry
            )
        )
        manager_annotations = dict(definitions.get("__annotations__", {}))
        for manager_name, value in definitions.items():
            if isinstance(value, Manager):
                manager_annotations.setdefault(
                    manager_name,
                    existing_annotations.get(manager_name, ClassVar[Any]),
                )
        if manager_annotations:
            definitions["__annotations__"] = {
                **existing_annotations,
                **manager_annotations,
            }
        definitions["__skip_registry__"] = True

        meta = type(
            "Meta",
            (),
            {
                "registry": False,
                "tablename": getattr(cls.meta, "tablename", None),
                "table_prefix": getattr(cls.meta, "table_prefix", None),
                "unique_together": list(getattr(cls.meta, "unique_together", []) or []),
                "indexes": list(getattr(cls.meta, "indexes", []) or []),
                "constraints": list(getattr(cls.meta, "constraints", []) or []),
                "reflect": getattr(cls.meta, "reflect", False),
                "abstract": getattr(cls.meta, "abstract", False),
                "model_engine": getattr(cls.meta, "model_engine", None),
                "is_tenant": getattr(cls.meta, "is_tenant", None),
                "register_default": getattr(cls.meta, "register_default", None),
            },
        )

        copied_model = create_saffier_model(
            name or cls.__name__,
            cls.__module__,
            __definitions__=definitions,
            __metadata__=meta,
            __qualname__=cls.__qualname__,
            __bases__=cls.__bases__,
        )
        copied_model.database = getattr(cls, "database", None)
        copied_model.__using_schema__ = getattr(cls, "__using_schema__", None)

        if registry is None:
            copied_model.meta.registry = False
            return copied_model
        return copied_model.add_to_registry(registry, on_conflict=on_conflict)

    copy_model = copy_saffier_model
    copy_edgy_model = copy_saffier_model

    @classmethod
    def real_add_to_registry(
        cls,
        *,
        registry: "saffier.Registry",
        name: str = "",
        database: bool | Any | str = "keep",
        on_conflict: str = "error",
    ) -> type["Model"]:
        """Attach a copied model class to another registry.

        This is the internal implementation behind `add_to_registry()`. It
        resolves naming conflicts, rebinds fields and managers to the target
        registry, rebuilds relation descriptors, and regenerates the proxy model
        so the attached class behaves like a first-class registered model.

        Args:
            registry: Target registry.
            name: Optional replacement model name.
            database: Database binding strategy or explicit database object.
            on_conflict: Conflict strategy for duplicate model names.

        Returns:
            type[Model]: The attached model class.

        Raises:
            ImproperlyConfigured: If a conflicting model already exists and the
                conflict strategy is `"error"`.
        """
        if getattr(cls.meta, "registry", None) not in (None, False, registry):
            return cls.copy_saffier_model(
                registry=registry,
                name=name or cls.__name__,
                on_conflict=on_conflict,
            )

        model_name = name or cls.__name__
        if model_name in registry.models:
            if on_conflict == "keep":
                return cast("type[Model]", registry.models[model_name])
            if on_conflict == "replace":
                registry.delete_model(model_name)
            else:
                raise ImproperlyConfigured(
                    f'A model with the same name is already registered: "{model_name}".'
                )

        cls.meta.registry = registry
        cls.__name__ = model_name

        if database is True:
            cls.database = registry.database
        elif database not in (False, "keep"):
            cls.database = database
        elif getattr(cls, "database", None) is None:
            cls.database = registry.database

        registry.models[model_name] = cls
        cls.__db_model__ = True
        cls.meta.model = cls
        cls.fields = cls.meta.fields
        cls._table = None
        cls._db_schemas = {}

        for field_name, field in cls.fields.items():
            field.owner = cls
            field.registry = registry
            if field.primary_key and field_name == cls.meta.pk_attribute:
                cls.pkname = field_name

        for manager_name in getattr(cls.meta, "managers", []):
            manager = getattr(cls, manager_name, None)
            if isinstance(manager, Manager):
                manager.name = manager_name
                manager.model_class = cls

        if getattr(cls.meta, "foreign_key_fields", None) and not cls.is_proxy_model:
            related_names = _set_related_name_for_foreign_keys(cls.meta.foreign_key_fields, cls)
            cls.meta.related_names.update(related_names)

        for field_name, field in list(cls.fields.items()):
            if isinstance(field, saffier.ManyToManyField):
                _set_many_to_many_relation(field, cls, field_name)

        _register_model_signals(cls)
        cls.__proxy_model__ = None
        if not cls.is_proxy_model and not cls.meta.abstract:
            proxy_model = cls.generate_proxy_model()
            cls.__proxy_model__ = proxy_model
            cls.__proxy_model__.parent = cls
            registry.models[model_name] = cls

        if hasattr(registry, "_handle_model_registration"):
            registry._handle_model_registration(cls)
        registry.execute_model_callbacks(cls)
        return cast("type[Model]", cls)

    @classmethod
    def add_to_registry(
        cls,
        registry: "saffier.Registry",
        name: str = "",
        database: bool | Any | str = "keep",
        *,
        on_conflict: str = "error",
    ) -> type["Model"]:
        """Attach the model to another registry, copying if required.

        Args:
            registry: Destination registry.
            name: Optional replacement model name.
            database: Database rebinding strategy.
            on_conflict: Conflict strategy for duplicate model names.

        Returns:
            type[Model]: Registered model class.
        """
        return cls.real_add_to_registry(
            registry=registry,
            name=name,
            database=database,
            on_conflict=on_conflict,
        )

    @classmethod
    def generate_proxy_model(cls) -> type["Model"]:
        """Generate the lightweight proxy model used for SQLAlchemy-style access.

        Proxy models mirror the field layout of the concrete model but stay
        detached from registry registration. They exist so class-level field
        access can emulate SQLAlchemy's declarative attribute style.

        Returns:
            type[Model]: Proxy model class for `cls`.
        """
        existing_proxy = cls.__dict__.get("__proxy_model__")
        if existing_proxy:
            return existing_proxy

        fields = {key: copy.copy(field) for key, field in cls.fields.items()}
        fields["__skip_registry__"] = True
        proxy_model = ProxyModel(
            name=cls.__name__,
            module=cls.__module__,
            metadata=cls.meta,
            definitions=fields,
        )

        proxy_model.build()
        generify_model_fields(proxy_model.model)
        return proxy_model.model

    @classmethod
    def build(cls, schema: str | None = None) -> sqlalchemy.Table:
        """Build the SQLAlchemy table for the model in the requested schema.

        Table generation expands multi-column fields, applies field-level global
        constraints, attaches `Meta`-declared indexes and constraints, and keeps
        schema-specific tables isolated from the shared registry metadata.

        Args:
            schema: Schema name to build against. `None` uses the registry
                default behavior.

        Returns:
            sqlalchemy.Table: Built or cached SQLAlchemy table for the model.
        """
        tablename = cls.meta.tablename
        registry = cls.meta.registry
        database = getattr(cls, "database", None)
        if database is not None and hasattr(registry, "metadata_by_url"):
            registry_metadata = cast(
                "sqlalchemy.MetaData", registry.metadata_by_url[str(database.url)]
            )
        else:
            registry_metadata = cast("sqlalchemy.MetaData", registry._metadata)  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(registry, "_schema_metadata_cache"):
            registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = registry.db_schema

        # Keep tenant/using table generation isolated from the shared registry
        # metadata. This prevents cross-schema table/index leakage in metadata.
        if schema == registry_schema:
            metadata = registry_metadata
            metadata.schema = schema
        else:
            if schema not in schema_metadata_cache:
                schema_metadata_cache[schema] = sqlalchemy.MetaData(schema=schema)
            metadata = schema_metadata_cache[schema]

        table_key = tablename if schema is None else f"{schema}.{tablename}"
        existing_table = metadata.tables.get(table_key)
        if existing_table is not None:
            return existing_table

        unique_together = cls.meta.unique_together
        index_constraints = cls.meta.indexes
        table_constraints = cls.meta.constraints

        columns = []
        field_constraints = []
        for name, field in cls.fields.items():
            if field.has_column():
                field_columns = list(field.get_columns(name))
                columns.extend(field_columns)
                field_constraints.extend(
                    field.get_global_constraints(name, field_columns, schema=schema)
                )

        # Handle the uniqueness together
        uniques = []
        for field in unique_together or []:
            unique_constraint = cls._get_unique_constraints(field)
            uniques.append(unique_constraint)

        # Handle the indexes
        indexes = []
        for field in index_constraints or []:
            index = cls._get_indexes(field)
            indexes.append(index)

        constraints = []
        for constraint in table_constraints or []:
            constraints.append(constraint)
        constraints.extend(field_constraints)

        return sqlalchemy.Table(
            tablename,
            metadata,
            *columns,
            *uniques,
            *indexes,
            *constraints,
            extend_existing=True,  # type: ignore
        )

    @classmethod
    def _get_unique_constraints(cls, columns: Sequence) -> sqlalchemy.UniqueConstraint | None:
        """
        Returns the unique constraints for the model.

        The columns must be a a list, tuple of strings or a UniqueConstraint object.
        """
        if isinstance(columns, str):
            expanded = cls._expand_constraint_field_names((columns,))
            return sqlalchemy.UniqueConstraint(*expanded)
        elif isinstance(columns, UniqueConstraint):
            expanded = cls._expand_constraint_field_names(columns.fields)
            return sqlalchemy.UniqueConstraint(*expanded)
        expanded = cls._expand_constraint_field_names(columns)
        return sqlalchemy.UniqueConstraint(*expanded)

    @classmethod
    def _get_indexes(cls, index: Index) -> sqlalchemy.Index | None:
        """Build a SQLAlchemy index from a Saffier `Index` declaration.

        Args:
            index: Declared Saffier index definition.

        Returns:
            sqlalchemy.Index | None: SQLAlchemy index object.
        """
        expanded = cls._expand_constraint_field_names(index.fields or ())
        return sqlalchemy.Index(index.name, *expanded)  # type: ignore

    @classmethod
    def _expand_constraint_field_names(cls, names: Sequence[str]) -> tuple[str, ...]:
        expanded: list[str] = []
        for name in names:
            field = cls.fields.get(name)
            if field is not None and hasattr(field, "get_column_names"):
                expanded.extend(field.get_column_names(name))
            else:
                expanded.append(name)
        return tuple(expanded)

    def update_from_dict(self, dict_values: dict[str, Any]) -> Self:
        """Assign values from a dictionary using normal attribute semantics.

        Returns:
            Self: The current instance for fluent usage.
        """
        for key, value in dict_values.items():
            setattr(self, key, value)
        return self

    def extract_db_fields(self, only: Sequence[str] | None = None) -> dict[str, Any]:
        """Collect persisted field values from the current instance.

        Args:
            only: Optional subset of logical field names to include.

        Returns:
            dict[str, Any]: Payload containing only database-backed fields.
        """
        if only is not None:
            allowed = set(only)
            return {
                k: v
                for k, v in self.__dict__.items()
                if k in allowed and k in self.fields and self.fields[k].has_column()
            }
        return {
            k: v
            for k, v in self.__dict__.items()
            if k in self.fields and self.fields[k].has_column()
        }

    @classmethod
    def extract_column_values(
        cls,
        extracted_values: dict[str, Any],
        is_update: bool = False,
        is_partial: bool = False,
        phase: str = "",
        instance: Any | None = None,
        model_instance: Any | None = None,
        evaluate_values: bool = False,
    ) -> dict[str, Any]:
        """Convert logical field payloads into database column payloads.

        The method runs field-specific normalization, expands multi-column
        fields such as composite foreign keys, injects defaults when allowed,
        and returns the final column-value mapping used by insert/update
        expressions.

        Args:
            extracted_values: Logical field payload keyed by Saffier field name.
            is_update: Whether the payload is for an update operation.
            is_partial: Whether the update payload omits untouched fields.
            phase: Context label exposed to field hooks through context vars.
            instance: Instance currently being persisted.
            model_instance: Original model instance used by nested helpers.
            evaluate_values: Whether callable payload values should be executed.

        Returns:
            dict[str, Any]: Database-ready payload keyed by SQL column name.
        """
        validated: dict[str, Any] = {}
        token = CURRENT_PHASE.set(phase)
        token2 = CURRENT_INSTANCE.set(instance)
        token3 = CURRENT_MODEL_INSTANCE.set(model_instance)
        field_dict: dict[str, Any] = {}
        token_field_ctx = CURRENT_FIELD_CONTEXT.set(field_dict)

        try:
            extracted_values = cls.normalize_field_kwargs(extracted_values)
            if evaluate_values:
                new_extracted_values: dict[str, Any] = {}
                for key, value in extracted_values.items():
                    if callable(value):
                        field_dict.clear()
                        field_dict["field"] = cls.meta.fields.get(key)
                        value = value()
                    new_extracted_values[key] = value
                extracted_values = new_extracted_values
            else:
                extracted_values = dict(extracted_values)

            if cls.meta.input_modifying_fields:
                for field_name in cls.meta.input_modifying_fields:
                    cls.meta.fields[field_name].modify_input(field_name, extracted_values)

            need_second_pass = []
            for field_name, field in cls.meta.fields.items():
                field_dict.clear()
                field_dict["field"] = field
                if field.validator.read_only:
                    if field_name in extracted_values:
                        for sub_name, value in field.clean(
                            field_name, extracted_values[field_name]
                        ).items():
                            if sub_name in validated:
                                raise ValueError(f"value set twice for key: {sub_name}")
                            validated[sub_name] = value
                    elif (
                        not is_partial or (field.inject_default_on_partial_update and is_update)
                    ) and field.has_default():
                        validated.update(field.get_default_values(field_name, validated))
                    continue
                if field_name in extracted_values:
                    item = extracted_values[field_name]
                    for sub_name, value in field.clean(field_name, item).items():
                        if sub_name in validated:
                            raise ValueError(f"value set twice for key: {sub_name}")
                        validated[sub_name] = value
                elif (
                    not is_partial or (field.inject_default_on_partial_update and is_update)
                ) and field.has_default():
                    need_second_pass.append(field)

            for field in need_second_pass:
                field_dict.clear()
                field_dict["field"] = field
                if field.name not in validated:
                    validated.update(field.get_default_values(field.name, validated))
        finally:
            CURRENT_FIELD_CONTEXT.reset(token_field_ctx)
            CURRENT_MODEL_INSTANCE.reset(token3)
            CURRENT_INSTANCE.reset(token2)
            CURRENT_PHASE.reset(token)
        return validated

    def __setattr__(self, key: Any, value: Any) -> Any:
        if key == "__using_schema__":
            self.__dict__.pop("_table", None)
        if key in self.fields:
            # Setting a relationship to a raw pk value should set a
            # fully-fledged relationship instance, with just the pk loaded.
            field = self.fields[key]
            if getattr(field, "is_computed", False):
                field.set_value(self, key, value)
                return
            if isinstance(field, saffier.ManyToManyField):
                value = getattr(self, settings.many_to_many_relation.format(key=key))
                super().__setattr__(key, value)
                return
            if field.is_virtual:
                if hasattr(field, "set_value") and not isinstance(field, saffier.ManyToManyField):
                    field.set_value(self, key, value)
                    return
                super().__setattr__(key, value)
                return
            if hasattr(field, "set_value") and not isinstance(field, saffier.ManyToManyField):
                field.set_value(self, key, value)
                return
            value = self.fields[key].expand_relationship(value)
        super().__setattr__(key, value)

    def __get_instance_values(self, instance: Any) -> set[tuple[str, Any]]:
        values: set[tuple[str, Any]] = set()
        for key, value in instance.__dict__.items():
            if key not in instance.fields or value is None:
                continue
            if hasattr(value, "pk"):
                value = value.pk
            try:
                hash(value)
            except TypeError:
                value = repr(value)
            values.add((key, value))
        return values

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, SaffierBaseModel):
            return False
        if self.meta.registry is not other.meta.registry:
            return False
        if self.meta.tablename != other.meta.tablename:
            return False

        for field_name in self.identifying_db_fields:
            left = getattr(self, field_name, None)
            right = getattr(other, field_name, None)
            if hasattr(left, "pk"):
                left = left.pk
            if hasattr(right, "pk"):
                right = right.pk
            if left != right:
                return False
        return True


class SaffierBaseReflectModel(SaffierBaseModel, metaclass=BaseModelReflectMeta):
    """Base class for database-reflected models.

    Reflected models reuse nearly all runtime behavior from `SaffierBaseModel`,
    but their table definition comes from an existing database rather than from
    declared Saffier fields. Reflection currently relies on the synchronous
    SQLAlchemy engine because async reflection support is intentionally kept out
    of the model layer.
    """

    @classmethod
    @functools.lru_cache
    def get_engine(cls, url: str) -> Engine:
        """Return a cached synchronous engine for reflection work.

        Args:
            url: Database URL used for reflection.

        Returns:
            Engine: Synchronous SQLAlchemy engine.
        """
        return sqlalchemy.create_engine(url)

    @property
    def pk(self) -> Any:
        return super().pk

    @pk.setter
    def pk(self, value: Any) -> Any:
        SaffierBaseModel.pk.fset(self, value)

    @classmethod
    def build(cls, schema: str | None = None) -> sqlalchemy.Table:
        """Return a reflected SQLAlchemy table for the requested schema.

        The reflected-model variant reuses the same schema-specific metadata
        caching strategy as concrete models, but populates tables by reflecting
        existing database objects instead of constructing them from field
        declarations.

        Args:
            schema: Schema name to reflect against.

        Returns:
            sqlalchemy.Table: Reflected table object.
        """
        registry = cls.meta.registry
        database = getattr(cls, "database", None)
        if database is not None and hasattr(registry, "metadata_by_url"):
            registry_metadata = cast(
                "sqlalchemy.MetaData", registry.metadata_by_url[str(database.url)]
            )
        else:
            registry_metadata = cast("sqlalchemy.MetaData", registry._metadata)  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(registry, "_schema_metadata_cache"):
            registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = registry.db_schema

        if schema == registry_schema:
            metadata = registry_metadata
            metadata.schema = schema
        else:
            if schema not in schema_metadata_cache:
                schema_metadata_cache[schema] = sqlalchemy.MetaData(schema=schema)
            metadata = schema_metadata_cache[schema]
        tablename: str = cast("str", cls.meta.tablename)
        table_key = tablename if schema is None else f"{schema}.{tablename}"
        existing_table = metadata.tables.get(table_key)
        if existing_table is not None:
            return existing_table
        return cls.reflect(tablename, metadata)

    @classmethod
    def reflect(cls, tablename: str, metadata: sqlalchemy.MetaData) -> sqlalchemy.Table:
        """Reflect one database table into the supplied metadata.

        Args:
            tablename: Database table name to reflect.
            metadata: Metadata container receiving the reflected table.

        Returns:
            sqlalchemy.Table: Reflected SQLAlchemy table.

        Raises:
            ImproperlyConfigured: If the table cannot be reflected.
        """
        try:
            database = getattr(cls, "database", None)
            autoload_with = (
                database.sync_engine
                if database is not None and getattr(database, "sync_engine", None) is not None
                else cls.meta.registry.sync_engine  # type: ignore[union-attr]
            )
            return sqlalchemy.Table(
                tablename,
                metadata,
                schema=metadata.schema,
                autoload_with=autoload_with,
            )
        except Exception as e:
            raise ImproperlyConfigured(
                detail=f"Table with the name {tablename} does not exist."
            ) from e
