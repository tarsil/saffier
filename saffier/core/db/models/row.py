from typing import TYPE_CHECKING, Any, Optional, Sequence, Type, cast

from sqlalchemy.engine.result import Row

if TYPE_CHECKING:
    from saffier import Model


class ModelRow:
    @classmethod
    def from_query_result(
        cls, row: Row, select_related: Optional[Sequence[Any]] = None
    ) -> Optional[Type["Model"]]:
        """
        Instantiate a model instance, given a database row.
        """
        item = {}

        if not select_related:
            select_related = []

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

        return cast("Type[Model]", cls(**item))
