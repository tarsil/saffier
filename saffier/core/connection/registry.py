import asyncio
import contextlib
import copy
import logging
from collections.abc import Callable, Generator, Sequence
from functools import cached_property
from typing import Any, ClassVar, cast

import sqlalchemy
from sqlalchemy import Engine
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import declarative_base as sa_declarative_base

from saffier._instance import Instance
from saffier.conf import _monkay, settings
from saffier.core.connection.database import Database
from saffier.core.connection.schemas import Schema
from saffier.core.db.constants import CASCADE
from saffier.core.utils.sync import current_eventloop, run_sync

logger = logging.getLogger(__name__)


class MetaDataDict(dict[str | None, sqlalchemy.MetaData]):
    def __init__(self, registry: "Registry") -> None:
        self.registry = registry
        super().__init__()

    def __getitem__(self, key: str | None) -> sqlalchemy.MetaData:
        if key not in self.registry.extra and key is not None:
            raise KeyError(f'Extra database "{key}" does not exist.')
        if key not in self:
            super().__setitem__(key, self.registry._make_metadata())
        return super().__getitem__(key)

    def get(self, key: str | None, default: Any = None) -> sqlalchemy.MetaData | Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __copy__(self) -> "MetaDataDict":
        cloned = MetaDataDict(registry=self.registry)
        for key, value in self.items():
            cloned[key] = copy.copy(value)
        return cloned

    copy = __copy__


class MetaDataByUrlDict(dict[str, str | None]):
    def __init__(self, registry: "Registry") -> None:
        self.registry = registry
        super().__init__()
        self.process()

    def process(self) -> None:
        self.clear()
        self[str(self.registry.database.url)] = None
        for name, database in self.registry.extra.items():
            self[str(database.url)] = name

    def __getitem__(self, key: str) -> sqlalchemy.MetaData:
        translated_name = super().__getitem__(key)
        return self.registry._metadata_by_name[translated_name]

    def get(self, key: str, default: Any = None) -> sqlalchemy.MetaData | Any:
        try:
            return self[key]
        except KeyError:
            return default

    def get_name(self, key: str) -> str | None:
        return cast("str | None", super().__getitem__(key))

    def __copy__(self) -> "MetaDataByUrlDict":
        return MetaDataByUrlDict(registry=self.registry)

    copy = __copy__


class Registry:
    """
    The command center for the models being generated
    for Saffier.
    """

    def __init__(
        self,
        database: Database | str,
        *,
        with_content_type: bool | type[Any] = False,
        **kwargs: Any,
    ) -> None:
        self.db_schema = kwargs.get("schema")
        self._automigrate_config = kwargs.pop("automigrate_config", None)
        self._is_automigrated: bool = False
        extra = kwargs.pop("extra", {}) or {}
        self.database: Database = (
            database if isinstance(database, Database) else Database(database)
        )
        self.models: dict[str, Any] = {}
        self.reflected: dict[str, Any] = {}
        self.pattern_models: dict[str, Any] = {}
        self.content_type: Any | None = None
        self.extra: dict[str, Database] = {
            name: value if isinstance(value, Database) else Database(value)
            for name, value in extra.items()
        }
        assert all(self.extra_name_check(name) for name in self.extra), (
            "Invalid name in extra detected. See logs for details."
        )
        self._pattern_reflected_dbs: set[str | None] = set()
        self._content_type_models_bound: set[str] = set()
        self._model_callbacks: dict[str, list[tuple[Callable[[type[Any]], None], bool]]] = {}

        self.schema = Schema(registry=self)
        self._metadata = self._make_metadata()
        self._metadata_by_name = MetaDataDict(self)
        self._metadata_by_name[None] = self._metadata
        for name in self.extra:
            self._metadata_by_name[name] = self._make_metadata()
        self._metadata_by_url = MetaDataByUrlDict(self)

        if with_content_type is not False:
            self._set_content_type(with_content_type)

    def _make_metadata(self) -> sqlalchemy.MetaData:
        if self.db_schema is not None:
            return sqlalchemy.MetaData(schema=self.db_schema)
        return sqlalchemy.MetaData()

    def extra_name_check(self, name: Any) -> bool:
        if not isinstance(name, str):
            logger.error("Extra database name: %r is not a string.", name)
            return False
        if not name.strip():
            logger.error('Extra database name: "%s" is empty.', name)
            return False
        if name.strip() != name:
            logger.warning(
                'Extra database name: "%s" starts or ends with whitespace characters.', name
            )
        return True

    def _get_relation_target_name(self, relation: Any) -> str | None:
        if isinstance(relation, str):
            return relation
        if isinstance(relation, type):
            return relation.__name__
        return None

    def _is_auto_through_model(self, model_class: type[Any]) -> bool:
        from saffier.core.db.fields.base import ManyToManyField

        for owner_model in self.models.values():
            for field_name, field in owner_model.fields.items():
                if not isinstance(field, ManyToManyField):
                    continue
                through_model = getattr(field, "through", None)
                if through_model is not model_class:
                    continue
                target_name = self._get_relation_target_name(field.to) or field.target.__name__
                expected_old_name = f"{owner_model.__name__}{target_name}"
                expected_old_table = f"{owner_model.__name__.lower()}s_{target_name}s".lower()

                expected_new_name = f"{owner_model.__name__}{field_name.capitalize()}Through"
                expected_new_table = expected_new_name.lower()
                if owner_model.meta.table_prefix:
                    expected_old_table = f"{owner_model.meta.table_prefix}_{expected_old_table}"
                    expected_new_table = f"{owner_model.meta.table_prefix}_{expected_new_table}"

                return (
                    model_class.__name__ == expected_old_name
                    and getattr(model_class.meta, "tablename", None) == expected_old_table
                ) or (
                    model_class.__name__ == expected_new_name
                    and getattr(model_class.meta, "tablename", None) == expected_new_table
                )
        return False

    def _copy_dependencies(self, model_class: type[Any], skipped: set[str]) -> set[str]:
        from saffier.core.db.fields.base import ForeignKey

        dependencies: set[str] = set()
        for field in model_class.fields.values():
            if isinstance(field, ForeignKey):
                target_name = self._get_relation_target_name(field.to)
                if (
                    target_name
                    and target_name in self.models
                    and target_name != model_class.__name__
                ):
                    dependencies.add(target_name)
        dependencies.difference_update(skipped)
        return dependencies

    def _sorted_model_names_for_copy(self) -> list[str]:
        skipped = {
            name
            for name, model_class in self.models.items()
            if self._is_auto_through_model(model_class)
        }
        remaining = {
            name: self._copy_dependencies(model_class, skipped)
            for name, model_class in self.models.items()
            if name not in skipped
        }
        ordered: list[str] = []
        resolved: set[str] = set()

        while remaining:
            ready = [name for name, deps in remaining.items() if deps.issubset(resolved)]
            if not ready:
                ordered.extend(remaining.keys())
                break
            for name in ready:
                ordered.append(name)
                resolved.add(name)
                remaining.pop(name)
        return ordered

    def _copy_model_to_registry(
        self,
        model_class: type[Any],
        registry: "Registry",
        *,
        pending_m2m_patches: list[tuple[str, str, str]],
    ) -> type[Any]:
        from saffier.core.db.fields.base import ForeignKey, ManyToManyField
        from saffier.core.db.models.managers import Manager
        from saffier.core.utils.models import create_saffier_model

        definitions: dict[str, Any] = {}
        manager_annotations: dict[str, Any] = {}
        existing_annotations = dict(getattr(model_class, "__annotations__", {}))
        for field_name, field in model_class.fields.items():
            field_copy = copy.copy(field)
            if hasattr(field_copy, "_target"):
                delattr(field_copy, "_target")
            if isinstance(field_copy, ForeignKey):
                target_name = self._get_relation_target_name(field_copy.to)
                if target_name and target_name in self.models:
                    field_copy.to = target_name
            elif isinstance(field_copy, ManyToManyField):
                target_name = self._get_relation_target_name(field_copy.to)
                if target_name and target_name in self.models:
                    field_copy.to = target_name

                through_name = self._get_relation_target_name(field_copy.through)
                if through_name and through_name in self.models:
                    if self._is_auto_through_model(self.models[through_name]):
                        field_copy.through = None
                    elif through_name in registry.models:
                        field_copy.through = registry.models[through_name]
                    else:
                        pending_m2m_patches.append(
                            (model_class.__name__, field_name, through_name)
                        )

            definitions[field_name] = field_copy

        for manager_name in getattr(model_class.meta, "managers", []):
            manager = getattr(model_class, manager_name, None)
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

        meta = type(
            "Meta",
            (),
            {
                "registry": registry,
                "tablename": getattr(model_class.meta, "tablename", None),
                "table_prefix": getattr(model_class.meta, "table_prefix", None),
                "unique_together": list(getattr(model_class.meta, "unique_together", []) or []),
                "indexes": list(getattr(model_class.meta, "indexes", []) or []),
                "constraints": list(getattr(model_class.meta, "constraints", []) or []),
                "reflect": getattr(model_class.meta, "reflect", False),
                "abstract": getattr(model_class.meta, "abstract", False),
            },
        )

        return create_saffier_model(
            model_class.__name__,
            model_class.__module__,
            __definitions__=definitions,
            __metadata__=meta,
            __qualname__=model_class.__qualname__,
            __bases__=model_class.__bases__,
        )

    def __copy__(self) -> "Registry":
        registry_copy = type(self)(
            self.database,
            schema=self.db_schema,
            extra=self.extra,
            automigrate_config=self._automigrate_config,
        )
        pending_m2m_patches: list[tuple[str, str, str]] = []

        for model_name in self._sorted_model_names_for_copy():
            self._copy_model_to_registry(
                self.models[model_name],
                registry_copy,
                pending_m2m_patches=pending_m2m_patches,
            )

        for model_name, model_class in self.reflected.items():
            if model_name in registry_copy.models or model_name in registry_copy.reflected:
                continue
            self._copy_model_to_registry(
                model_class,
                registry_copy,
                pending_m2m_patches=pending_m2m_patches,
            )

        for owner_name, field_name, through_name in pending_m2m_patches:
            from saffier.core.db.fields.base import ManyToManyField
            from saffier.core.db.relationships.relation import Relation

            through_model = registry_copy.models.get(through_name) or registry_copy.reflected.get(
                through_name
            )
            if through_model is None:
                continue
            owner_model = registry_copy.models[owner_name]
            field = cast("ManyToManyField", owner_model.fields[field_name])
            field.through = through_model
            setattr(
                owner_model,
                settings.many_to_many_relation.format(key=field_name),
                Relation(through=through_model, to=field.target, owner=owner_model),
            )

        registry_copy.pattern_models = dict(self.pattern_models)
        if hasattr(self, "tenant_models") and hasattr(registry_copy, "tenant_models"):
            registry_copy.tenant_models = {
                name: model
                for name in self.tenant_models
                if (model := registry_copy.models.get(name) or registry_copy.reflected.get(name))
                is not None
            }
        registry_copy._pattern_reflected_dbs = set(self._pattern_reflected_dbs)
        registry_copy._content_type_models_bound = set(self._content_type_models_bound)
        if self.content_type is not None:
            with_content_type = registry_copy.models.get(
                "ContentType"
            ) or registry_copy.reflected.get("ContentType")
            if with_content_type is None:
                with_content_type = self.content_type
            registry_copy.content_type = with_content_type
            registry_copy._attach_content_type_to_registered_models()
        return registry_copy

    def _set_content_type(self, with_content_type: bool | type[Any]) -> None:
        from saffier.contrib.contenttypes.models import ContentType

        content_type_model = ContentType if with_content_type is True else with_content_type
        if not isinstance(content_type_model, type):
            raise TypeError("with_content_type must be True/False or a model type.")

        if getattr(content_type_model.meta, "abstract", False):
            meta = type(
                "Meta",
                (),
                {
                    "registry": self,
                    "tablename": "contenttypes",
                },
            )
            content_type_model = type("ContentType", (content_type_model,), {"Meta": meta})
        elif getattr(content_type_model.meta, "registry", None) in (None, False):
            if not getattr(content_type_model.meta, "tablename", None):
                content_type_model.meta.tablename = "contenttypes"
            content_type_model = content_type_model.add_to_registry(self, name="ContentType")

        registered_content_type = self.models.get("ContentType")
        if registered_content_type is not None:
            content_type_model = registered_content_type

        self.content_type = content_type_model
        self._attach_content_type_to_registered_models()

    def _attach_content_type_to_registered_models(self) -> None:
        if self.content_type is None:
            return
        for model in self.models.values():
            self._attach_content_type_to_model(model)

    def _handle_model_registration(self, model_class: type[Any]) -> None:
        if self.content_type is None:
            return
        self._attach_content_type_to_model(model_class)

    def _attach_content_type_to_model(self, model_class: type[Any]) -> None:
        if self.content_type is None:
            return
        if model_class in (self.content_type, getattr(self.content_type, "proxy_model", None)):
            return
        if getattr(model_class.meta, "abstract", False):
            return
        if getattr(model_class, "is_proxy_model", False):
            return
        if model_class.__name__ in self.reflected:
            return

        from saffier.contrib.contenttypes.fields import ContentTypeField
        from saffier.core.db.models.metaclasses import _set_related_name_for_foreign_keys

        if "content_type" in model_class.fields:
            if isinstance(model_class.fields["content_type"], ContentTypeField):
                if getattr(model_class.meta, "is_tenant", False):
                    model_class.fields["content_type"].no_constraint = True
                target_registry = getattr(self.content_type.meta, "registry", None)
                if (
                    getattr(model_class.meta, "registry", None) is not target_registry
                    or getattr(model_class, "database", None)
                    is not getattr(self.content_type, "database", None)
                    or getattr(model_class.meta, "is_tenant", False)
                ):
                    self.content_type.__require_model_based_deletion__ = True
                self._bind_content_type_pre_save(model_class)
            return

        has_content_type_field = any(
            isinstance(field, ContentTypeField) for field in model_class.fields.values()
        )
        if has_content_type_field:
            content_type_fields = {
                field_name: field
                for field_name, field in model_class.fields.items()
                if isinstance(field, ContentTypeField)
            }
            for field_name, field in content_type_fields.items():
                field.owner = model_class
                field.registry = self
                if getattr(model_class.meta, "is_tenant", False):
                    field.no_constraint = True
                if isinstance(field.to, str) and field.to == "ContentType":
                    field.to = self.content_type
                    if hasattr(field, "_target"):
                        delattr(field, "_target")
                auto_related_names = {
                    model_class.__name__.lower(),
                    f"{model_class.__name__.lower()}s_set",
                }
                desired_related_name = (
                    f"reverse_{model_class.__name__.lower()}"
                    if field.related_name in auto_related_names or field.related_name is None
                    else field.related_name
                )

                if desired_related_name not in model_class.meta.related_names:
                    if field.related_name in model_class.meta.related_names:
                        previous_related_name = cast("str", field.related_name)
                        model_class.meta.related_names.discard(previous_related_name)
                        model_class.meta.related_fields.pop(previous_related_name, None)
                        model_class.meta.related_names_mapping.pop(previous_related_name, None)

                        target_meta = field.target.meta
                        target_meta.related_fields.pop(previous_related_name, None)
                        target_meta.related_names_mapping.pop(previous_related_name, None)
                        target_meta.fields.pop(previous_related_name, None)
                        target_meta.fields_mapping.pop(previous_related_name, None)
                        if hasattr(field.target, previous_related_name):
                            delattr(field.target, previous_related_name)
                        proxy_target = getattr(field.target, "proxy_model", None)
                        if proxy_target is not None and hasattr(
                            proxy_target, previous_related_name
                        ):
                            delattr(proxy_target, previous_related_name)

                    field.related_name = desired_related_name
                    related_names = _set_related_name_for_foreign_keys(
                        {field_name: field},
                        cast(Any, model_class),
                    )
                    model_class.meta.related_names.update(related_names)
                target_registry = getattr(self.content_type.meta, "registry", None)
                if (
                    getattr(model_class.meta, "registry", None) is not target_registry
                    or getattr(model_class, "database", None)
                    is not getattr(self.content_type, "database", None)
                    or getattr(model_class.meta, "is_tenant", False)
                ):
                    self.content_type.__require_model_based_deletion__ = True
            self._bind_content_type_pre_save(model_class)
            return

        related_name = f"reverse_{model_class.__name__.lower()}"
        if hasattr(self.content_type, related_name):
            raise RuntimeError(
                f"Duplicate related content type name generated: {related_name!r} for {model_class!r}"
            )

        field = ContentTypeField(
            to=self.content_type,
            related_name=related_name,
            on_delete=CASCADE,
            no_constraint=(
                getattr(self.content_type, "no_constraint", False)
                or getattr(model_class.meta, "is_tenant", False)
            ),
        )
        # ContentType is managed by registry pre-save hooks.
        field.validator.read_only = True
        field.name = "content_type"
        field.owner = model_class
        field.registry = self
        model_class.fields["content_type"] = field
        model_class.meta.fields["content_type"] = field
        model_class.meta.fields_mapping["content_type"] = field
        model_class.meta.foreign_key_fields["content_type"] = field

        model_related_names = _set_related_name_for_foreign_keys(
            {"content_type": field},
            cast(Any, model_class),
        )
        model_class.meta.related_names.update(model_related_names)

        if (
            getattr(model_class.meta, "registry", None)
            is not getattr(self.content_type.meta, "registry", None)
            or getattr(model_class, "database", None)
            is not getattr(self.content_type, "database", None)
            or getattr(model_class.meta, "is_tenant", False)
        ):
            self.content_type.__require_model_based_deletion__ = True

        self._bind_content_type_pre_save(model_class)

        self._clear_model_table_cache(model_class)
        model_class.__proxy_model__ = None
        proxy_model = model_class.generate_proxy_model()
        model_class.__proxy_model__ = proxy_model
        model_class.__proxy_model__.parent = model_class

    def _clear_model_table_cache(self, model_class: type[Any]) -> None:
        model_class._table = None
        model_class._db_schemas = {}

        table_name = cast("str | None", getattr(model_class.meta, "tablename", None))
        if table_name is None:
            return

        metadata_pool = [self._metadata]
        metadata_pool.extend(getattr(self, "_schema_metadata_cache", {}).values())

        for metadata in metadata_pool:
            table_keys = {table_name}
            if metadata.schema:
                table_keys.add(f"{metadata.schema}.{table_name}")
            for table_key in table_keys:
                existing_table = metadata.tables.get(table_key)
                if existing_table is not None:
                    metadata.remove(existing_table)

    def _bind_content_type_pre_save(self, model_class: type[Any]) -> None:
        if model_class.__name__ in self._content_type_models_bound:
            return
        if self.content_type is None:
            return
        from saffier.contrib.contenttypes.fields import ContentTypeField

        async def ensure_content_type(
            sender: type[Any],
            instance: Any,
            **kwargs: Any,
        ) -> None:
            if self.content_type is None:
                return
            for field_name, field in sender.fields.items():
                if not isinstance(field, ContentTypeField):
                    continue
                current_content_type = instance.__dict__.get(field_name)
                if current_content_type is None and field.null:
                    continue
                if (
                    current_content_type is not None
                    and getattr(current_content_type, "pk", None) is not None
                ):
                    continue
                payload = {}
                if current_content_type is not None and hasattr(
                    current_content_type, "extract_db_fields"
                ):
                    payload = current_content_type.extract_db_fields()

                payload["name"] = sender.__name__
                payload["schema_name"] = instance.get_active_instance_schema()
                content_type_obj = await self.content_type.query.create(**payload)
                setattr(instance, field_name, content_type_obj)

        model_class.signals.pre_save.connect(ensure_content_type)
        self._content_type_models_bound.add(model_class.__name__)

    @property
    def metadata(self) -> Any:
        for model_class in self.models.values():
            model_class.build(schema=self.db_schema)
        return self.metadata_by_name[None]

    @metadata.setter
    def metadata(self, value: sqlalchemy.MetaData) -> None:
        self._metadata = value
        self._metadata_by_name[None] = value
        self._metadata_by_url.process()

    @property
    def metadata_by_name(self) -> MetaDataDict:
        for model_class in self.models.values():
            model_class.build(schema=self.db_schema)
        for model_class in self.reflected.values():
            try:
                model_class.build(schema=self.db_schema)
            except Exception:
                # Reflected models may require an active engine or an existing table.
                # Migration preparation should not fail just because reflection is unavailable.
                continue
        return self._metadata_by_name

    @metadata_by_name.setter
    def metadata_by_name(
        self, value: MetaDataDict | dict[str | None, sqlalchemy.MetaData]
    ) -> None:
        metadata_dict = MetaDataDict(self)
        for key, metadata in value.items():
            metadata_dict[key] = metadata
        if None not in metadata_dict:
            metadata_dict[None] = self._make_metadata()
        self._metadata_by_name = metadata_dict
        self._metadata = metadata_dict[None]
        self._metadata_by_url.process()

    @property
    def metadata_by_url(self) -> MetaDataByUrlDict:
        return self._metadata_by_url

    @property
    def metadatas(self) -> dict[str | None, sqlalchemy.MetaData]:
        return self.metadata_by_name

    @cached_property
    def declarative_base(self) -> Any:
        if self.db_schema:
            metadata = sqlalchemy.MetaData(schema=self.db_schema)
        else:
            metadata = sqlalchemy.MetaData()
        return sa_declarative_base(metadata=metadata)

    @property
    def engine(self) -> AsyncEngine:
        assert self.database.engine, "database not started, no engine found."
        return self.database.engine

    @property
    def sync_engine(self) -> Engine:
        return self.engine.sync_engine

    async def create_all(
        self,
        refresh_metadata: bool = True,
        databases: Sequence[str | None] = (None,),
    ) -> None:
        self._attach_content_type_to_registered_models()
        if refresh_metadata:
            await self.arefresh_metadata(multi_schema=True)
        await self.schema.create_schema(
            self.db_schema,
            if_not_exists=True,
            init_models=True,
            update_cache=bool(self.db_schema),
            databases=databases,
        )

    async def drop_all(self, databases: Sequence[str | None] = (None,)) -> None:
        await self.schema.drop_schema(
            self.db_schema,
            cascade=True,
            if_exists=True,
            databases=databases,
        )

    def _iter_databases(self) -> list[tuple[str | None, Database]]:
        databases: list[tuple[str | None, Database]] = [(None, self.database)]
        for name, db in self.extra.items():
            databases.append((name, db))
        return databases

    def get_model(
        self,
        model_name: str,
        *,
        include_content_type_attr: bool = True,
        include_reflected: bool = True,
        include_pattern: bool = False,
    ) -> Any:
        if (
            include_content_type_attr
            and model_name == "ContentType"
            and self.content_type is not None
        ):
            return self.content_type
        if model_name in self.models:
            model = self.models[model_name]
            if getattr(model, "is_proxy_model", False):
                parent = getattr(model, "parent", None)
                if (
                    parent is not None
                    and getattr(getattr(parent, "meta", None), "registry", None) is self
                ):
                    return parent
            return model
        if include_reflected and model_name in self.reflected:
            return self.reflected[model_name]
        if include_pattern and model_name in self.pattern_models:
            return self.pattern_models[model_name]
        raise LookupError(f"Registry doesn't have a {model_name} model.")

    def delete_model(self, model_name: str) -> bool:
        for model_dict in (self.models, self.reflected, self.pattern_models):
            if model_name in model_dict:
                del model_dict[model_name]
                return True
        return False

    def register_callback(
        self,
        model_reference: str | type[Any],
        callback: Callable[[type[Any]], None],
        *,
        one_time: bool = False,
    ) -> None:
        model_name = (
            model_reference if isinstance(model_reference, str) else model_reference.__name__
        )
        callbacks = self._model_callbacks.setdefault(model_name, [])
        callbacks.append((callback, one_time))

        model_class = self.models.get(model_name) or self.reflected.get(model_name)
        if model_class is None or getattr(model_class, "is_proxy_model", False):
            return
        callback(model_class)
        if one_time:
            callbacks.remove((callback, one_time))
            if not callbacks:
                self._model_callbacks.pop(model_name, None)

    def execute_model_callbacks(self, model_class: type[Any]) -> None:
        if getattr(model_class, "is_proxy_model", False):
            return
        callbacks = list(self._model_callbacks.get(model_class.__name__, ()))
        if not callbacks:
            return

        remaining: list[tuple[Callable[[type[Any]], None], bool]] = []
        for callback, one_time in callbacks:
            callback(model_class)
            if not one_time:
                remaining.append((callback, one_time))

        if remaining:
            self._model_callbacks[model_class.__name__] = remaining
        else:
            self._model_callbacks.pop(model_class.__name__, None)

    def init_models(
        self, *, init_column_mappers: bool = True, init_class_attrs: bool = True
    ) -> None:
        for model_class in self.models.values():
            model_class.meta.full_init(
                init_column_mappers=init_column_mappers,
                init_class_attrs=init_class_attrs,
            )
        for model_class in self.reflected.values():
            model_class.meta.full_init(
                init_column_mappers=init_column_mappers,
                init_class_attrs=init_class_attrs,
            )

    def invalidate_models(self, *, clear_class_attrs: bool = True) -> None:
        for model_class in self.models.values():
            model_class.meta.invalidate(clear_class_attrs=clear_class_attrs)
        for model_class in self.reflected.values():
            model_class.meta.invalidate(clear_class_attrs=clear_class_attrs)

    def get_tablenames(self) -> set[str]:
        tables = set()
        for model_class in self.models.values():
            tables.add(model_class.meta.tablename)
        for model_class in self.reflected.values():
            tables.add(model_class.meta.tablename)
        return tables

    def _automigrate_update(self, migration_settings: Any) -> None:
        from saffier.cli.base import upgrade

        self._is_automigrated = True
        with _monkay.with_full_overwrite(
            extensions={},
            settings=migration_settings,
            instance=Instance(registry=self),
            apply_extensions=True,
            evaluate_settings_with={
                "on_conflict": "replace",
                "ignore_import_errors": False,
                "ignore_preload_import_errors": False,
            },
        ):
            upgrade(app=None)

    async def _automigrate(self) -> None:
        migration_settings = self._automigrate_config
        if migration_settings is None or not _monkay.settings.allow_automigrations:
            self._is_automigrated = True
            return
        await asyncio.to_thread(self._automigrate_update, migration_settings)

    async def reflect_pattern_models(
        self,
        *,
        database_name: str | None = None,
        database: Database | None = None,
    ) -> None:
        if not self.pattern_models:
            return
        if database_name in self._pattern_reflected_dbs:
            return

        target_db = database
        if target_db is None:
            target_db = self.database if database_name is None else self.extra[database_name]

        schemes: set[None | str] = set()
        patterns = []
        for pattern_model in self.pattern_models.values():
            meta = pattern_model.meta
            if database_name not in meta.databases:
                continue
            schemes.update(meta.schemes)
            patterns.append(pattern_model)

        if not patterns:
            self._pattern_reflected_dbs.add(database_name)
            return

        tmp_metadata = sqlalchemy.MetaData()
        for schema in schemes:
            await target_db.run_sync(self._reflect_schema_metadata, tmp_metadata, schema)

        for table in tmp_metadata.tables.values():
            for pattern_model in patterns:
                meta = pattern_model.meta
                if table.schema not in meta.schemes:
                    continue
                if not meta.include_pattern.match(table.name):
                    continue
                if meta.exclude_pattern and meta.exclude_pattern.match(table.name):
                    continue
                if pattern_model.fields_not_supported_by_table(table):
                    continue

                model_name = meta.template(table)
                try:
                    self.get_model(model_name, include_pattern=False)
                except LookupError:
                    ...
                else:
                    raise RuntimeError(
                        f"Conflicting reflected model name generated: {model_name!r}."
                    )

                pattern_model.create_reflected_model(
                    table=table,
                    registry=self,
                    database=target_db,
                    name=model_name,
                )

        self._pattern_reflected_dbs.add(database_name)

    @staticmethod
    def _reflect_schema_metadata(
        connection: Any,
        metadata: sqlalchemy.MetaData,
        schema: str | None,
    ) -> None:
        inspector = sqlalchemy.inspect(connection)
        table_names = inspector.get_table_names(schema=schema)
        for table_name in table_names:
            try:
                sqlalchemy.Table(
                    table_name,
                    metadata,
                    schema=schema,
                    autoload_with=connection,
                )
            except NoSuchTableError:
                continue

    async def __aenter__(self) -> "Registry":
        connected: list[Database] = []
        try:
            for name, database in self._iter_databases():
                await database.connect()
                connected.append(database)
                if not self._is_automigrated:
                    await self._automigrate()
                await self.reflect_pattern_models(database_name=name, database=database)
        except Exception:
            for database in reversed(connected):
                if database.is_connected:
                    await database.disconnect()
            raise
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        for _, database in reversed(self._iter_databases()):
            if database.is_connected:
                await database.disconnect()

    @contextlib.contextmanager
    def with_async_env(
        self, loop: asyncio.AbstractEventLoop | None = None
    ) -> Generator["Registry", None, None]:
        close = False
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = current_eventloop.get()
                if loop is None:
                    loop = asyncio.new_event_loop()
                    close = True

        token = current_eventloop.set(loop)
        try:
            yield cast("Registry", run_sync(self.__aenter__(), loop=loop))
        finally:
            run_sync(self.__aexit__(), loop=loop)
            current_eventloop.reset(token)
            if close:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

    def refresh_metadata(
        self,
        *,
        update_only: bool = False,
        multi_schema: bool | str | object = False,
        ignore_schema_pattern: str | object | None = None,
    ) -> "Registry":
        """
        Rebuild metadata containers used by migrations and schema reflection.

        The current Saffier implementation keeps the refresh intentionally simple:
        it clears cached table objects and reinitialises the per-database metadata
        containers so subsequent `build()` calls recreate the SQLAlchemy tables.
        """
        del multi_schema, ignore_schema_pattern

        if not update_only:
            self._metadata = self._make_metadata()
            self._metadata_by_name = MetaDataDict(self)
            self._metadata_by_name[None] = self._metadata
            for name in self.extra:
                self._metadata_by_name[name] = self._make_metadata()
            self._metadata_by_url.process()
        self._schema_metadata_cache = {}

        for collection in (self.models, self.reflected):
            for model_class in collection.values():
                model_class._table = None
                model_class._db_schemas = {}

        return self

    async def arefresh_metadata(
        self,
        *,
        update_only: bool = False,
        multi_schema: bool | str | object = False,
        ignore_schema_pattern: str | object | None = None,
    ) -> "Registry":
        return self.refresh_metadata(
            update_only=update_only,
            multi_schema=multi_schema,
            ignore_schema_pattern=ignore_schema_pattern,
        )
