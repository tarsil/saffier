import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Type, Union, cast

from sqlalchemy.engine.result import Row

from saffier.core.db.models.base import SaffierBaseModel
from saffier.exceptions import QuerySetError

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Model, Prefetch, QuerySet


class ModelRow(SaffierBaseModel):
    @classmethod
    def from_query_result(
        cls,
        row: Row,
        select_related: Optional[Sequence[Any]] = None,
        prefetch_related: Optional[Sequence["Prefetch"]] = None,
        is_only_fields: bool = False,
        only_fields: Sequence[str] = None,
        is_defer_fields: bool = False,
        exclude_secrets: bool = False,
        using_schema: Union[str, None] = None,
    ) -> Optional[Type["Model"]]:
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
        item: Dict[str, Any] = {}
        select_related = select_related or []
        prefetch_related = prefetch_related or []

        secret_fields = (
            [name for name, field in cls.fields.items() if field.secret] if exclude_secrets else []
        )

        # Instantiate any child instances first.
        for related in select_related:
            if "__" in related:
                first_part, remainder = related.split("__", 1)
                try:
                    model_cls = cls.fields[first_part].target
                except KeyError:
                    model_cls = getattr(cls, first_part).related_from

                item[first_part] = model_cls.from_query_result(
                    row,
                    select_related=[remainder],
                    using_schema=using_schema,
                    exclude_secrets=exclude_secrets,
                )
            else:
                try:
                    model_cls = cls.fields[related].target
                except KeyError:
                    model_cls = getattr(cls, related).related_from
                item[related] = model_cls.from_query_result(
                    row, using_schema=using_schema, exclude_secrets=exclude_secrets
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

            child_item = {}
            for column in model_related.table.columns:
                if column.name in secret_fields or related in secret_fields:
                    continue
                if column.name not in cls.fields.keys():
                    continue
                elif related not in child_item:
                    if getattr(row, related) is not None:
                        child_item[column.name] = getattr(row, related)

            # Make sure we generate a temporary reduced model
            # For the related fields. We simply chnage the structure of the model
            # and rebuild it with the new fields.
            if related not in secret_fields:
                item[related] = model_related.proxy_model(**child_item)

        # Check for the only_fields
        if is_only_fields or is_defer_fields:
            mapping_fields = (
                [str(field) for field in only_fields] if is_only_fields else list(row._mapping.keys())  # type: ignore
            )

            for column, value in row._mapping.items():
                if column in secret_fields:
                    continue
                # Making sure when a table is reflected, maps the right fields of the ReflectModel
                if column not in mapping_fields:
                    continue

                if column not in item:
                    item[column] = value

            # We need to generify the model fields to make sure we can populate the
            # model without mandatory fields
            model = cast("Type[Model]", cls.proxy_model(**item))

            # Apply the schema to the model
            model = cls.__apply_schema(model, using_schema)

            model = cls.__handle_prefetch_related(
                row=row, model=model, prefetch_related=prefetch_related
            )
            return model
        else:
            # Pull out the regular column values.
            for column in cls.table.columns:
                if column.key in secret_fields:
                    continue
                # Making sure when a table is reflected, maps the right fields of the ReflectModel
                if column.key not in cls.fields:
                    continue
                elif column.key not in item:
                    if column in row._mapping:
                        item[column.key] = row._mapping[column]
                    elif column.key in row._mapping:
                        item[column.key] = row._mapping[column.key]

        model = (
            cast("Type[Model]", cls(**item))
            if not exclude_secrets
            else cast("Type[Model]", cls.proxy_model(**item))
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
    def __apply_schema(cls, model: Type["Model"], schema: Optional[str] = None) -> Type["Model"]:
        # Apply the schema to the model
        if schema is not None:
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
        model: Type["Model"],
        prefetch_related: Sequence["Prefetch"],
        parent_cls: Optional[Type["Model"]] = None,
        original_prefetch: Optional["Prefetch"] = None,
        is_nested: bool = False,
    ) -> Type["Model"]:
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
                filter_by_pk = getattr(row, cls.pkname)
                extra = {f"{related.related_name}__id": filter_by_pk}
                related.queryset.extra = extra

                # Execute the queryset
                records = asyncio.get_event_loop().run_until_complete(
                    cls.__run_query(queryset=related.queryset)
                )
                setattr(model, related.to_attr, records)
            else:
                model_cls = getattr(cls, related.related_name).related_from
                records = cls.__process_nested_prefetch_related(
                    row,
                    prefetch_related=related,
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    queryset=original_prefetch.queryset,
                )

                setattr(model, related.to_attr, records)
        return model

    @classmethod
    def __process_nested_prefetch_related(
        cls,
        row: Row,
        prefetch_related: "Prefetch",
        parent_cls: Type["Model"],
        original_prefetch: "Prefetch",
        queryset: "QuerySet",
    ) -> List[Type["Model"]]:
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

        # Extact foreign key value
        filter_by_pk = getattr(row, parent_cls.pkname)

        extra = {f"{query}__id": filter_by_pk}

        records = asyncio.get_event_loop().run_until_complete(
            cls.__run_query(model_class, extra, queryset)
        )
        return records

    @classmethod
    async def __run_query(
        cls,
        model: Optional[Type["Model"]] = None,
        extra: Optional[Dict[str, Any]] = None,
        queryset: Optional["QuerySet"] = None,
    ) -> Union[List[Type["Model"]], Any]:
        """
        Runs a specific query against a given model with filters.
        """

        if not queryset:
            return await model.query.filter(**extra)  # type: ignore

        if extra:
            queryset.extra = extra

        return await queryset
