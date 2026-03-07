import functools
from typing import TYPE_CHECKING, Any

from saffier.exceptions import RelationshipIncompatible, RelationshipNotFound
from saffier.protocols.many_relationship import ManyRelationProtocol

if TYPE_CHECKING:
    from saffier import Model, ReflectModel


class Relation(ManyRelationProtocol):
    """
    When a `related_name` is generated, creates a RelatedField from the table pointed
    from the ForeignKey declaration and the the table declaring it.
    """

    def __init__(
        self,
        instance: type["Model"] | type["ReflectModel"] | None = None,
        through: type["Model"] | type["ReflectModel"] | None = None,
        to: type["Model"] | type["ReflectModel"] | None = None,
        owner: type["Model"] | type["ReflectModel"] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.through = through
        self.instance = instance
        self.to = to
        self.owner = owner

        # Relationship parameters
        self.owner_name = self.owner.__name__.lower()  # type: ignore
        self.to_name = (
            self.to.lower()
            if isinstance(self.to, str)
            else self.to.__name__.lower()  # type: ignore[union-attr]
        )
        self._relation_params = {
            self.owner_name: None,
            self.to_name: None,
        }

    @property
    def resolved_to(self) -> type["Model"] | type["ReflectModel"]:
        if isinstance(self.to, str):
            registry = self.owner.meta.registry if self.owner is not None else None  # type: ignore[union-attr]
            if registry is None:
                raise RelationshipNotFound(detail=f"Could not resolve target model '{self.to}'.")
            resolved = registry.models.get(self.to) or registry.reflected.get(self.to)
            if resolved is None:
                raise RelationshipNotFound(detail=f"Could not resolve target model '{self.to}'.")
            self.to = resolved
        return self.to  # type: ignore[return-value]

    @property
    def resolved_through(self) -> type["Model"] | type["ReflectModel"]:
        if isinstance(self.through, str):
            registry = self.owner.meta.registry if self.owner is not None else None  # type: ignore[union-attr]
            if registry is None:
                raise RelationshipNotFound(detail=f"Could not resolve through model '{self.through}'.")
            resolved = registry.models.get(self.through) or registry.reflected.get(self.through)
            if resolved is None:
                raise RelationshipNotFound(detail=f"Could not resolve through model '{self.through}'.")
            self.through = resolved
        return self.through  # type: ignore[return-value]

    def _relation_queryset(self) -> Any:
        through = self.resolved_through
        manager = through.meta.manager  # type: ignore[attr-defined]
        schema = None
        if self.instance is not None and hasattr(self.instance, "get_active_instance_schema"):
            schema = self.instance.get_active_instance_schema()

        if schema is None:
            return manager.get_queryset()

        return manager.queryset_class(
            through,
            using_schema=schema,
            table=through.table_schema(schema),
            database=getattr(self.instance, "database", getattr(through, "database", None)),
        )

    def __get__(self, instance: Any, owner: Any) -> Any:
        return self.__class__(
            instance=instance, through=self.through, to=self.to, owner=self.owner
        )

    def __getattr__(self, item: Any) -> Any:
        """
        Gets the attribute from the queryset and if it does not
        exist, then lookup in the model.
        """
        through = self.resolved_through
        queryset = self._relation_queryset()
        try:
            attr = getattr(queryset, item)
        except AttributeError:
            attr = getattr(through, item)

        func = self.wrap_args(attr)
        return func

    def wrap_args(self, func: Any) -> Any:
        @functools.wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            kwargs[self.owner_name] = self.instance.pk  # type: ignore
            return func(*args, **kwargs)

        return wrapped

    async def add(self, child: type["Model"]) -> None:
        """
        Adds a child to the model as a list

        . Validates the type of the child being added to the relationship and raises error for
        if the type is wrong.
        . Checks if the middle table already contains the record being added. Raises error if yes.
        """
        target = self.resolved_to
        if not isinstance(child, target):
            raise RelationshipIncompatible(
                f"The child is not from the type '{target.__name__}'."
            )

        self._relation_params.update({self.owner_name: self.instance, self.to_name: child})  # type: ignore
        queryset = self._relation_queryset()
        exists = await queryset.filter(**self._relation_params).exists()  # type: ignore

        if not exists:
            await queryset.create(**self._relation_params)  # type: ignore

    async def remove(self, child: type["Model"]) -> None:
        """Removes a child from the list of many to many.

        . Validates if there is a relationship between the entities.
        . Removes the field if there is
        """
        target = self.resolved_to
        if not isinstance(child, target):
            raise RelationshipIncompatible(
                f"The child is not from the type '{target.__name__}'."
            )

        self._relation_params.update({self.owner_name: self.instance, self.to_name: child})  # type: ignore
        queryset = self._relation_queryset()
        exists = await queryset.filter(**self._relation_params).exists()  # type: ignore

        if not exists:
            raise RelationshipNotFound(
                detail=f"There is no relationship between '{self.owner_name}' and '{self.to_name}: {child.pk}'."
            )

        child = await queryset.filter(**self._relation_params).get()  # type: ignore
        await child.delete()  # type: ignore

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.resolved_through.__name__}"
