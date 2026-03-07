import copy
import inspect
from collections import deque
from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Union,
    cast,
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


class MetaInfo:
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
        "_needs_special_serialization",
    )

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pk: Field | None = getattr(meta, "pk", None)
        self.pk_attribute: Field | str = getattr(meta, "pk_attribute", "")
        self.abstract: bool = getattr(meta, "abstract", False)
        fields = getattr(meta, "fields", None)
        if fields is None:
            fields = getattr(meta, "fields_mapping", {})
        self.fields: dict[str, Field] = dict(fields or {})
        self.fields_mapping: dict[str, Field] = self.fields
        self.registry: Registry | None = getattr(meta, "registry", None)
        self.tablename: str | None = getattr(meta, "tablename", None)
        self.table_prefix: str | None = getattr(meta, "table_prefix", None)
        self.parents: Any = getattr(meta, "parents", [])
        self.many_to_many_fields: set[str] = set(getattr(meta, "many_to_many_fields", set()))
        self.foreign_key_fields: dict[str, Any] = dict(getattr(meta, "foreign_key_fields", {}))
        self.one_to_one_fields: set[Any] = set(getattr(meta, "one_to_one_fields", set()))
        self.model: type[Model] | None = None
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
        self.special_getter_fields: set[str] = set(
            getattr(meta, "special_getter_fields", set()) or []
        )
        self.secret_fields: set[str] = set(getattr(meta, "secret_fields", set()) or [])
        self._needs_special_serialization: bool | None = getattr(
            meta, "_needs_special_serialization", None
        )

    @property
    def needs_special_serialization(self) -> bool:
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


def _is_sqlalchemy_compatibility_enabled(model_class: type) -> bool:
    for base in type.__getattribute__(model_class, "__mro__"):
        if base.__dict__.get("__saffier_sqlalchemy_compatibility__", False):
            return True
    return False


def _check_model_inherited_registry(bases: tuple[type, ...]) -> Registry:
    """
    When a registry is missing from the Meta class, it should look up for the bases
    and obtain the first found registry.

    If not found, then a ImproperlyConfigured exception is raised.
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
    """
    Returns a meta attribute either from the direct Meta class or from parent model metas.
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
    """
    When an abstract class is declared, we must treat the manager's value coming from the top.
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
    """
    Sets the related name for the foreign keys.
    When a `related_name` is generated, creates a RelatedField from the table pointed
    from the ForeignKey declaration and the the table declaring it.
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

        def bind_related_name(target_model: type[Any]) -> None:
            existing_related = getattr(target_model, default_related_name, None)
            if existing_related is not None:
                if (
                    isinstance(existing_related, RelatedField)
                    and existing_related.related_from is model_class
                ):
                    existing_mapping = model_class.meta.related_names_mapping.get(
                        default_related_name
                    )
                    if existing_mapping not in (None, name):
                        raise ForeignKeyBadConfigured(
                            f"Multiple related_name with the same value '{default_related_name}' found to the same target. Related names must be different."
                        )
                    model_class.meta.related_fields[default_related_name] = existing_related
                    model_class.meta.related_names_mapping[default_related_name] = name
                    return
                if not isinstance(existing_related, RelatedField):
                    raise ForeignKeyBadConfigured(
                        f"Multiple related_name with the same value '{default_related_name}' found to the same target. Related names must be different."
                    )

            related_field = RelatedField(
                related_name=default_related_name,
                related_to=target_model,
                related_from=model_class,
                embed_parent=getattr(foreign_key, "embed_parent", None),
            )

            target_models = [target_model]
            proxy_target = target_model.__dict__.get("__proxy_model__")
            if proxy_target is not None and proxy_target not in target_models:
                target_models.append(proxy_target)
            for candidate in target_models:
                setattr(candidate, default_related_name, related_field)

            model_class.meta.related_fields[default_related_name] = related_field
            target_meta = cast("MetaInfo", target_model.meta)
            target_meta.related_fields[default_related_name] = related_field
            if default_related_name not in target_meta.fields:
                placeholder = saffier_fields.PlaceholderField(
                    name=default_related_name,
                    no_copy=True,
                    inherit=False,
                )
                placeholder.owner = target_model
                placeholder.registry = target_meta.registry
                target_meta.fields[default_related_name] = placeholder
                target_meta.fields_mapping[default_related_name] = placeholder

            model_class.meta.related_names_mapping[default_related_name] = name
            target_meta.related_names_mapping[default_related_name] = name

            if (
                getattr(foreign_key, "no_constraint", False)
                and getattr(foreign_key, "on_delete", None) == saffier.CASCADE
            ) or getattr(foreign_key, "force_cascade_deletion_relation", False):
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

    if isinstance(m2m.through, str):
        if registry is not None: # type: ignore
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
    """
    Registers the signals in the model's Broadcaster and sets the defaults.
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
    if getattr(field, "no_copy", False):
        return field
    return copy.copy(field)


class BaseModelMeta(type):
    __slots__ = ()

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        attrs: Any,
        meta_info_class: type[MetaInfo] = MetaInfo,
        register_content_type: bool = True,
    ) -> Any:
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
                    if is_pk_present:
                        raise ImproperlyConfigured(
                            f"Cannot create model {name} with multiple primary keys."
                        )
                    is_pk_present = True
                    pk_attribute = key

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

            if meta.unique_together:
                raise ImproperlyConfigured("unique_together cannot be in abstract classes.")

            if meta.indexes:
                raise ImproperlyConfigured("indexes cannot be in abstract classes.")
            if meta.constraints:
                raise ImproperlyConfigured("constraints cannot be in abstract classes.")
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
            if field.primary_key:
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
        """
        Returns a db_schema from the model registry, if available.
        """
        meta = getattr(cls, "meta", None)
        if meta is None or getattr(meta, "registry", None) is None:
            return None
        return cast("str | None", meta.registry.db_schema)

    def get_db_shema(cls) -> str | None:
        """
        Returns a db_schema from registry if any is passed.
        """
        return cls.get_db_schema()

    @property
    def table(cls) -> Any:
        """
        Making sure the tables on inheritance state, creates the new
        one properly.

        Making sure the following scenarios are met:

        1. If there is a context_db_schema, it will return for those, which means, the `using`
        if being utilised.
        2. If a db_schema in the `registry` is passed, then it will use that as a default.
        3. If none is passed, defaults to the shared schema of the database connected.
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
        """
        Making sure the tables on inheritance state, creates the new
        one properly.

        The use of context vars instead of using the lru_cache comes from
        a warning from `ruff` where lru can lead to memory leaks.
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
        """
        Returns the signals of a class
        """
        return cast("Broadcaster", cls.meta.signals)

    def transaction(cls, *, force_rollback: bool = False, **kwargs: Any) -> Any:
        return cls.database.transaction(force_rollback=force_rollback, **kwargs)

    @property
    def proxy_model(cls) -> Any:
        """
        Returns the proxy_model from the Model when called using the cache.
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


class ModelMeta(metaclass=BaseModelMeta): ...


class ReflectMeta(metaclass=BaseModelReflectMeta): ...
