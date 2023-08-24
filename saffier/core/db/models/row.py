import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Type, Union, cast

from sqlalchemy.engine.result import Row

from saffier.exceptions import QuerySetError

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Model, Prefetch, QuerySet


class ModelRow:
    @classmethod
    def from_query_result(
        cls,
        row: Row,
        select_related: Optional[Sequence[Any]] = None,
        prefetch_related: Optional[Sequence["Prefetch"]] = None,
    ) -> Optional[Type["Model"]]:
        """
        Instantiate a model instance, given a database row.
        """
        item: Dict[str, Any] = {}
        select_related = select_related or []
        prefetch_related = prefetch_related or []

        # Instantiate any child instances first.
        for related in select_related:
            if "__" in related:
                first_part, remainder = related.split("__", 1)
                try:
                    model_cls = cls.fields[first_part].target
                except KeyError:
                    model_cls = getattr(cls, first_part).related_from

                item[first_part] = model_cls.from_query_result(row, select_related=[remainder])
            else:
                try:
                    model_cls = cls.fields[related].target
                except KeyError:
                    model_cls = getattr(cls, related).related_from
                item[related] = model_cls.from_query_result(row)

        # Pull out the regular column values.
        for column in cls.table.columns:
            # Making sure when a table is reflected, maps the right fields of the ReflectModel
            if column.name not in cls.fields.keys():
                continue

            elif column.name not in item:
                item[column.name] = row[column]

        model = cast("Type[Model]", cls(**item))
        model = cls.handle_prefetch_related(
            row=row, model=model, prefetch_related=prefetch_related
        )
        return model

        # return cast("Type[Model]", cls(**item))

    @classmethod
    def handle_prefetch_related(
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
                model_cls.handle_prefetch_related(
                    row,
                    model,
                    prefetch_related=[remainder_prefetch],
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    is_nested=True,
                )

            # Check for individual not nested querysets
            elif related.queryset is not None and not is_nested:
                filter_by_pk = row[cls.pkname]
                extra = {f"{related.related_name}__id": filter_by_pk}
                related.queryset.extra = extra

                # Execute the queryset
                records = asyncio.get_event_loop().run_until_complete(
                    cls.run_query(queryset=related.queryset)
                )
                setattr(model, related.to_attr, records)
            else:
                model_cls = getattr(cls, related.related_name).related_from
                records = cls.process_nested_prefetch_related(
                    row,
                    prefetch_related=related,
                    original_prefetch=original_prefetch,
                    parent_cls=model,
                    queryset=original_prefetch.queryset,
                )

                setattr(model, related.to_attr, records)
        return model

    @classmethod
    def process_nested_prefetch_related(
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
        filter_by_pk = row[parent_cls.pkname]

        extra = {f"{query}__id": filter_by_pk}

        records = asyncio.get_event_loop().run_until_complete(
            cls.run_query(model_class, extra, queryset)
        )
        return records

    @classmethod
    async def run_query(
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
