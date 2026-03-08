from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy.engine.result import Row

from saffier.core.db import fields as saffier_fields
from saffier.core.db.models.base import SaffierBaseModel
from saffier.core.utils.sync import run_sync
from saffier.exceptions import QuerySetError

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Model, Prefetch, QuerySet

saffier_setattr = object.__setattr__


class ModelRow(SaffierBaseModel):
    @staticmethod
    def _row_value(row: Row, key: str) -> Any:
        if key in row._mapping:
            return row._mapping[key]
        return getattr(row, key, None)

    @classmethod
    def _table_row_value(cls, row: Row, table: Any, key: str) -> Any:
        column = getattr(getattr(table, "c", None), key, None)
        if column is not None and column in row._mapping:
            return row._mapping[column]
        return cls._row_value(row, key)

    @classmethod
    def _build_related_pk_filter(cls, path: str, row: Row, model_class: Any) -> dict[str, Any]:
        target_class = model_class if isinstance(model_class, type) else type(model_class)
        return {
            f"{path}__{pk_name}": cls._row_value(row, pk_name) for pk_name in target_class.pknames
        }

    @classmethod
    async def apply_prefetch_related(
        cls,
        row: Row,
        model: type["Model"],
        prefetch_related: Sequence["Prefetch"],
    ) -> type["Model"]:
        if not prefetch_related:
            return model
        return await cls.__handle_prefetch_related_async(
            row=row,
            model=model,
            prefetch_related=prefetch_related,
        )

    @classmethod
    def from_query_result(
        cls,
        row: Row,
        select_related: Sequence[Any] | None = None,
        prefetch_related: Sequence["Prefetch"] | None = None,
        is_only_fields: bool = False,
        only_fields: Sequence[str] = None,
        is_defer_fields: bool = False,
        exclude_secrets: bool = False,
        using_schema: str | None = None,
        reference_select: dict[str, Any] | None = None,
        tables_and_models: dict[str, tuple[Any, Any]] | None = None,
        root_model_class: type["Model"] | None = None,
        prefix: str = "",
    ) -> type["Model"] | None:
        """
        Class method to convert a SQLAlchemy Row result into a SaffierModel row type.

        Looping through select_related fields if the query comes from a select_related operation.
        Validates if exists the select_related and related_field inside the models.

        When select_related and related_field exist for the same field being validated, the related
        field is ignored as it won't override the value already collected from the select_related.

        If there is no select_related, then goes through the related field where it **should**
        only return the instance of the the ForeignKey with the ID, making it lazy loaded.

        :return: Model class.
        """
        item: dict[str, Any] = {}
        select_related = select_related or []
        prefetch_related = prefetch_related or []
        reference_select = reference_select or {}
        root_model_class = root_model_class or cast("type[Model]", cls)
        if tables_and_models is not None and prefix in tables_and_models:
            model_table = tables_and_models[prefix][0]
        else:
            model_table = cls.table_schema(using_schema) if using_schema is not None else cls.table

        secret_fields = cls.meta.secret_fields if exclude_secrets else set()

        # Instantiate any child instances first.
        for related in select_related:
            if "__" in related:
                first_part, remainder = related.split("__", 1)
                try:
                    model_cls = cls.fields[first_part].target
                except (KeyError, AttributeError):
                    model_cls = getattr(cls, first_part).related_from

                item[first_part] = model_cls.from_query_result(
                    row,
                    select_related=[remainder],
                    using_schema=using_schema,
                    exclude_secrets=exclude_secrets,
                    tables_and_models=tables_and_models,
                    root_model_class=root_model_class,
                    prefix=(first_part if not prefix else f"{prefix}__{first_part}"),
                )
            else:
                try:
                    model_cls = cls.fields[related].target
                except (KeyError, AttributeError):
                    model_cls = getattr(cls, related).related_from
                item[related] = model_cls.from_query_result(
                    row,
                    using_schema=using_schema,
                    exclude_secrets=exclude_secrets,
                    tables_and_models=tables_and_models,
                    root_model_class=root_model_class,
                    prefix=(related if not prefix else f"{prefix}__{related}"),
                )

        # Populate the related names
        # Making sure if the model being queried is not inside a select related
        # This way it is not overritten by any value
        for related, foreign_key in cls.meta.foreign_key_fields.items():
            ignore_related: bool = cls.__should_ignore_related_name(related, select_related)
            if ignore_related:
                continue

            model_related = foreign_key.target

            # Apply the schema to the model
            model_related = cls.__apply_schema(model_related, using_schema)

            child_item: dict[str, Any] = {}
            if related not in secret_fields:
                column_names = (
                    foreign_key.get_column_names(related)
                    if hasattr(foreign_key, "get_column_names")
                    else (related,)
                )
                related_keys = (
                    tuple(foreign_key.related_columns.keys())
                    if hasattr(foreign_key, "related_columns")
                    else (model_related.pkname,)
                )
                for related_key, column_name in zip(related_keys, column_names, strict=False):
                    foreign_key_value = cls._table_row_value(row, model_table, column_name)
                    if foreign_key_value is not None:
                        child_item[related_key] = foreign_key_value

            # Make sure we generate a temporary reduced model
            # For the related fields. We simply chnage the structure of the model
            # and rebuild it with the new fields.
            if related not in secret_fields:
                if not child_item and getattr(foreign_key, "null", False):
                    related_instance = model_related()
                    if exclude_secrets:
                        related_instance.__no_load_trigger_attrs__.update(
                            model_related.meta.secret_fields
                        )
                    if using_schema is not None:
                        related_instance.table = model_related.table_schema(using_schema)
                    item[related] = related_instance
                else:
                    related_instance = model_related(**child_item)
                    if exclude_secrets:
                        related_instance.__no_load_trigger_attrs__.update(
                            model_related.meta.secret_fields
                        )
                    if using_schema is not None:
                        related_instance.table = model_related.table_schema(using_schema)
                    item[related] = related_instance

        # Check for the only_fields
        if is_only_fields or is_defer_fields:
            mapping_fields = (
                [str(field) for field in only_fields]
                if is_only_fields
                else list(row._mapping.keys())  # type: ignore
            )

            for column, value in row._mapping.items():
                column_name = str(getattr(column, "key", column))
                mapped_field = cls.meta.columns_to_field.get(column_name)
                if mapped_field is None:
                    continue
                if mapped_field in secret_fields:
                    continue
                # Making sure when a table is reflected, maps the right fields of the ReflectModel
                if mapped_field not in mapping_fields and column_name not in mapping_fields:
                    continue
                if column_name not in item:
                    item[column_name] = value

            # We need to generify the model fields to make sure we can populate the
            # model without mandatory fields
            model = cast("type[Model]", cls.proxy_model(**item))

            cls.__apply_reference_select(
                model=model,
                row=row,
                references=reference_select,
                tables_and_models=tables_and_models,
                root_model_class=root_model_class,
                using_schema=using_schema,
            )

            # Apply the schema to the model
            model = cls.__apply_schema(model, using_schema)

            model = cls.__handle_prefetch_related(
                row=row, model=model, prefetch_related=prefetch_related
            )
            return model
        else:
            # Pull out the regular column values.
            for column in model_table.columns:
                mapped_field = cls.meta.columns_to_field.get(column.key)
                if mapped_field is None:
                    continue
                if mapped_field in secret_fields:
                    continue
                if mapped_field in item and (
                    column.key == mapped_field
                    or isinstance(
                        cls.fields.get(mapped_field),
                        (saffier_fields.ForeignKey, saffier_fields.OneToOneField),
                    )
                ):
                    continue
                if column.key not in item:
                    if column in row._mapping:
                        item[column.key] = row._mapping[column]
                    elif column.key in row._mapping:
                        item[column.key] = row._mapping[column.key]

        model = (
            cast("type[Model]", cls(**item))
            if not exclude_secrets
            else cast("type[Model]", cls.proxy_model(**item))
        )
        if exclude_secrets:
            model.__no_load_trigger_attrs__.update(cls.meta.secret_fields)

        cls.__apply_reference_select(
            model=model,
            row=row,
            references=reference_select,
            tables_and_models=tables_and_models,
            root_model_class=root_model_class,
            using_schema=using_schema,
        )

        # Apply the schema to the model
        model = cls.__apply_schema(model, using_schema)

        # Handle prefetch related fields.
        model = cls.__handle_prefetch_related(
            row=row, model=model, prefetch_related=prefetch_related
        )

        if using_schema is not None:
            model.table = model.build(using_schema)  # type: ignore
        return model

    @classmethod
    def __apply_reference_select(
        cls,
        model: type["Model"] | None,
        row: Row,
        references: dict[str, Any],
        tables_and_models: dict[str, tuple[Any, Any]] | None,
        root_model_class: type["Model"],
        using_schema: str | None = None,
    ) -> None:
        if model is None:
            return

        for target, source in references.items():
            if isinstance(source, dict):
                child = getattr(model, target, None)
                if child is not None:
                    cls.__apply_reference_select(
                        model=child,
                        row=row,
                        references=source,
                        tables_and_models=tables_and_models,
                        root_model_class=root_model_class,
                        using_schema=using_schema,
                    )
                continue

            if source is None:
                continue

            value = cls.__resolve_reference_source(
                row=row,
                source=source,
                tables_and_models=tables_and_models,
                root_model_class=root_model_class,
                using_schema=using_schema,
            )
            setattr(model, target, value)

    @classmethod
    def __resolve_reference_source(
        cls,
        row: Row,
        source: Any,
        tables_and_models: dict[str, tuple[Any, Any]] | None,
        root_model_class: type["Model"],
        using_schema: str | None = None,
    ) -> Any:
        if source in row._mapping:
            return row._mapping[source]

        source_key = getattr(source, "key", None) or getattr(source, "name", None)
        if source_key is not None and source_key in row._mapping:
            return row._mapping[source_key]

        if isinstance(source, str):
            column = cls.__resolve_reference_column(
                source=source,
                tables_and_models=tables_and_models,
                root_model_class=root_model_class,
                using_schema=using_schema,
            )
            if column is not None:
                if column in row._mapping:
                    return row._mapping[column]
                if column.key in row._mapping:
                    return row._mapping[column.key]
            if source in row._mapping:
                return row._mapping[source]
            if hasattr(row, source):
                return getattr(row, source)

        raise QuerySetError(
            detail=f"Unable to resolve reference_select source '{source}' for {cls.__name__}."
        )

    @classmethod
    def __resolve_reference_column(
        cls,
        source: str,
        tables_and_models: dict[str, tuple[Any, Any]] | None,
        root_model_class: type["Model"],
        using_schema: str | None = None,
    ) -> Any | None:
        table = None
        column_name = source

        if "__" in source:
            prefix, column_name = source.rsplit("__", 1)
            if tables_and_models is not None:
                table = tables_and_models.get(prefix, (None, None))[0]
        elif tables_and_models is not None:
            table = tables_and_models.get("", (None, None))[0]

        if table is None:
            table = (
                root_model_class.table_schema(using_schema)
                if using_schema is not None
                else root_model_class.table
            )

        return getattr(table.c, column_name, None)

    @classmethod
    def __apply_schema(cls, model: type["Model"], schema: str | None = None) -> type["Model"]:
        # Apply the schema to model instances without mutating class-level table caches.
        if schema is not None and not isinstance(model, type):
            model.table = model.build(schema)  # type: ignore
        return model

    @classmethod
    def __should_ignore_related_name(
        cls, related_name: str, select_related: Sequence[str]
    ) -> bool:
        """
        Validates if it should populate the related field if select related is not considered.
        """
        for related_field in select_related:
            fields = related_field.split("__")
            if related_name in fields:
                return True
        return False

    @classmethod
    def __handle_prefetch_related(
        cls,
        row: Row,
        model: type["Model"],
        prefetch_related: Sequence["Prefetch"],
        parent_cls: type["Model"] | None = None,
        original_prefetch: Optional["Prefetch"] = None,
        is_nested: bool = False,
    ) -> type["Model"]:
        """
        Handles any prefetch related scenario from the model.
        Loads in advance all the models needed for a specific record

        Recursively checks for the related field and validates if there is any conflicting
        attribute. If there is, a `QuerySetError` is raised.
        """
        if not parent_cls:
            parent_cls = model

        for related in prefetch_related:
            if not original_prefetch:
                original_prefetch = related

            if original_prefetch and not is_nested:
                original_prefetch = related

            # Check for conflicting names
            # If to_attr has the same name of any
            if hasattr(parent_cls, original_prefetch.to_attr):
                raise QuerySetError(
                    f"Conflicting attribute to_attr='{original_prefetch.related_name}' with '{original_prefetch.to_attr}' in {parent_cls.__class__.__name__}"
                )

            if "__" in related.related_name:
                first_part, remainder = related.related_name.split("__", 1)
                if isinstance(
                    cls.fields.get(first_part), saffier_fields.ManyToManyField
                ) or hasattr(model, first_part):
                    records = run_sync(
                        cls.__collect_prefetch_records(
                            model=model,
                            related_name=related.related_name,
                            queryset=original_prefetch.queryset,
                        )
                    )
                    saffier_setattr(model, related.to_attr, records)
                    continue

                model_cls = cls.meta.related_fields[first_part].related_to

                # Build the new nested Prefetch object
                remainder_prefetch = related.__class__(
                    related_name=remainder, to_attr=related.to_attr, queryset=related.queryset
                )

                # Recursively continue the process of handling the
                # new prefetch
                model_cls.__handle_prefetch_related(
                    row,
                    model,
                    prefetch_related=[remainder_prefetch],
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    is_nested=True,
                )

            # Check for individual not nested querysets
            elif related.queryset is not None and not is_nested:
                extra = cls._build_related_pk_filter(related.related_name, row, cls)
                related.queryset.extra = extra

                # Execute the queryset
                records = run_sync(cls.__run_query(queryset=related.queryset))
                saffier_setattr(model, related.to_attr, records)
            elif isinstance(
                cls.fields.get(related.related_name),
                saffier_fields.ManyToManyField,
            ) or hasattr(model, related.related_name):
                records = run_sync(
                    cls.__collect_prefetch_records(
                        model=model,
                        related_name=related.related_name,
                        queryset=related.queryset,
                    )
                )
                saffier_setattr(model, related.to_attr, records)
            else:
                model_cls = getattr(cls, related.related_name).related_from
                records = cls.__process_nested_prefetch_related(
                    row,
                    prefetch_related=related,
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    queryset=original_prefetch.queryset,
                )

                saffier_setattr(model, related.to_attr, records)
        return model

    @classmethod
    async def __handle_prefetch_related_async(
        cls,
        row: Row,
        model: type["Model"],
        prefetch_related: Sequence["Prefetch"],
        parent_cls: type["Model"] | None = None,
        original_prefetch: Optional["Prefetch"] = None,
        is_nested: bool = False,
    ) -> type["Model"]:
        if not parent_cls:
            parent_cls = model

        for related in prefetch_related:
            if not original_prefetch:
                original_prefetch = related

            if original_prefetch and not is_nested:
                original_prefetch = related

            if hasattr(parent_cls, original_prefetch.to_attr):
                raise QuerySetError(
                    f"Conflicting attribute to_attr='{original_prefetch.related_name}' with '{original_prefetch.to_attr}' in {parent_cls.__class__.__name__}"
                )

            if "__" in related.related_name:
                first_part, remainder = related.related_name.split("__", 1)
                if isinstance(
                    cls.fields.get(first_part), saffier_fields.ManyToManyField
                ) or hasattr(model, first_part):
                    records = await cls.__collect_prefetch_records(
                        model=model,
                        related_name=related.related_name,
                        queryset=original_prefetch.queryset,
                    )
                    saffier_setattr(model, related.to_attr, records)
                    continue

                model_cls = cls.meta.related_fields[first_part].related_to
                remainder_prefetch = related.__class__(
                    related_name=remainder,
                    to_attr=related.to_attr,
                    queryset=related.queryset,
                )
                await model_cls.__handle_prefetch_related_async(
                    row,
                    model,
                    prefetch_related=[remainder_prefetch],
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    is_nested=True,
                )
            elif related.queryset is not None and not is_nested:
                extra = cls._build_related_pk_filter(related.related_name, row, cls)
                related.queryset.extra = extra
                records = await cls.__run_query(queryset=related.queryset)
                saffier_setattr(model, related.to_attr, records)
            elif isinstance(
                cls.fields.get(related.related_name),
                saffier_fields.ManyToManyField,
            ) or hasattr(model, related.related_name):
                records = await cls.__collect_prefetch_records(
                    model=model,
                    related_name=related.related_name,
                    queryset=related.queryset,
                )
                saffier_setattr(model, related.to_attr, records)
            else:
                records = await cls.__process_nested_prefetch_related_async(
                    row=row,
                    prefetch_related=related,
                    parent_cls=model,
                    original_prefetch=original_prefetch,
                    queryset=original_prefetch.queryset,
                )
                saffier_setattr(model, related.to_attr, records)
        return model

    @classmethod
    def __process_nested_prefetch_related(
        cls,
        row: Row,
        prefetch_related: "Prefetch",
        parent_cls: type["Model"],
        original_prefetch: "Prefetch",
        queryset: "QuerySet",
    ) -> list[type["Model"]]:
        """
        Processes the nested prefetch related names.
        """
        query_split = original_prefetch.related_name.split("__")
        query_split.reverse()
        query_split.pop(query_split.index(prefetch_related.related_name))

        # Get the model to query related
        model_class = getattr(cls, prefetch_related.related_name).related_from

        # Get the foreign key name from the model_class
        foreign_key_name = model_class.meta.related_names_mapping[prefetch_related.related_name]

        # Insert as the entry point of the query
        query_split.insert(0, foreign_key_name)

        # Build new filter
        query = "__".join(query_split)

        extra = cls._build_related_pk_filter(query, row, parent_cls)

        records = run_sync(cls.__run_query(model_class, extra, queryset))
        return records

    @classmethod
    async def __process_nested_prefetch_related_async(
        cls,
        row: Row,
        prefetch_related: "Prefetch",
        parent_cls: type["Model"],
        original_prefetch: "Prefetch",
        queryset: "QuerySet",
    ) -> list[type["Model"]]:
        query_split = original_prefetch.related_name.split("__")
        query_split.reverse()
        query_split.pop(query_split.index(prefetch_related.related_name))

        model_class = getattr(cls, prefetch_related.related_name).related_from
        foreign_key_name = model_class.meta.related_names_mapping[prefetch_related.related_name]
        query_split.insert(0, foreign_key_name)

        query = "__".join(query_split)
        extra = cls._build_related_pk_filter(query, row, parent_cls)

        return await cls.__run_query(model_class, extra, queryset)

    @classmethod
    async def __collect_prefetch_records(
        cls,
        model: type["Model"],
        related_name: str,
        queryset: Optional["QuerySet"] = None,
    ) -> list[type["Model"]]:
        records = await cls.__traverse_prefetch_path(model, related_name.split("__"))
        if queryset is None:
            return records
        if not records:
            return []

        filter_values = []
        for record in records:
            pk = getattr(record, "pk", None)
            if pk is not None and pk not in filter_values:
                filter_values.append(pk)

        if not filter_values:
            return []

        cloned_queryset = queryset._clone() if hasattr(queryset, "_clone") else queryset
        return await cloned_queryset.filter(pk__in=filter_values)

    @classmethod
    async def __traverse_prefetch_path(
        cls,
        model: type["Model"],
        path_parts: Sequence[str],
    ) -> list[type["Model"]]:
        if not path_parts:
            return [model]

        attr = getattr(model, path_parts[0], None)
        if attr is None:
            return []

        if hasattr(attr, "all"):
            values = await attr.all()
            results: list[type[Model]] = []
            for value in values:
                results.extend(await cls.__traverse_prefetch_path(value, path_parts[1:]))
            return results

        return await cls.__traverse_prefetch_path(attr, path_parts[1:])

    @classmethod
    async def __run_query(
        cls,
        model: type["Model"] | None = None,
        extra: dict[str, Any] | None = None,
        queryset: Optional["QuerySet"] = None,
    ) -> list[type["Model"]] | Any:
        """
        Runs a specific query against a given model with filters.
        """

        if not queryset:
            return await model.query.filter(**extra)  # type: ignore

        if extra:
            queryset.extra = extra

        return await queryset
