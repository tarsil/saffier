from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from saffier.exceptions import ObjectNotFound, RelationshipIncompatible, RelationshipNotFound
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
        through: type["Model"] | type["ReflectModel"] | str | None = None,
        to: type["Model"] | type["ReflectModel"] | str | None = None,
        owner: type["Model"] | type["ReflectModel"] | None = None,
        from_foreign_key: str = "",
        to_foreign_key: str = "",
        reverse: bool = False,
        embed_through: str | bool = False,
        refs: Any = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.through = through
        self.instance = instance
        self.to = to
        self.owner = owner
        self.reverse = reverse
        self.embed_through = embed_through
        self.from_foreign_key = from_foreign_key
        self.to_foreign_key = to_foreign_key
        self.refs: list[Any] = []

        # Relationship parameters
        self.owner_name = from_foreign_key or self.owner.__name__.lower()  # type: ignore[union-attr]
        self.to_name = to_foreign_key or (
            self.to.lower() if isinstance(self.to, str) else self.to.__name__.lower()  # type: ignore[union-attr]
        )
        self._relation_params = {
            self.owner_name: None,
            self.to_name: None,
        }
        if refs:
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes, bytearray)):
                refs = [refs]
            self.stage(*refs)

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
                raise RelationshipNotFound(
                    detail=f"Could not resolve through model '{self.through}'."
                )
            resolved = registry.models.get(self.through) or registry.reflected.get(self.through)
            if resolved is None:
                raise RelationshipNotFound(
                    detail=f"Could not resolve through model '{self.through}'."
                )
            self.through = resolved
        return self.through  # type: ignore[return-value]

    def _relation_queryset(self) -> Any:
        through = self.resolved_through
        manager = getattr(through, "query_related", None)
        if manager is None:
            manager = through.meta.manager  # type: ignore[attr-defined]
        schema = None
        if self.instance is not None and hasattr(self.instance, "get_active_instance_schema"):
            schema = self.instance.get_active_instance_schema()

        if schema is None:
            queryset = manager.get_queryset()
        else:
            queryset = manager.queryset_class(
                through,
                using_schema=schema,
                table=through.table_schema(schema),
                database=getattr(self.instance, "database", getattr(through, "database", None)),
            )

        if self.instance is None:
            return queryset

        queryset = queryset.filter(**{self.owner_name: self.instance.pk})

        if self.embed_through is not False:
            queryset.embed_parent = (self.to_name, self.embed_through or "")
            queryset.embed_parent_filters = queryset.embed_parent
            if self.to_name not in queryset._select_related:
                queryset._select_related.append(self.to_name)
        return queryset

    def stage(self, *children: Any) -> None:
        target = self.resolved_to
        for child in children:
            if not isinstance(child, (target, dict)):
                raise RelationshipIncompatible(
                    f"The child is not from the type '{target.__name__}'."
                )
            self.refs.append(child)

    async def save_related(self) -> None:
        while self.refs:
            await self.add(self.refs.pop(0))

    def _build_relation_params(self, child: Any) -> dict[str, Any]:
        owner_value = self.instance
        if hasattr(owner_value, "pk"):
            owner_pk = getattr(owner_value, "pk", None)
            if owner_pk is not None:
                owner_value = owner_pk

        child_value = child
        if hasattr(child_value, "pk"):
            child_pk = getattr(child_value, "pk", None)
            if child_pk is not None:
                child_value = child_pk

        return {
            self.owner_name: owner_value,
            self.to_name: child_value,
        }

    def _bind_embedded_through(self, child: Any, through_instance: Any) -> Any:
        if self.embed_through and isinstance(self.embed_through, str):
            setattr(child, self.embed_through, through_instance)
        return child

    @property
    def target_foreign_key(self) -> Any:
        return self.resolved_through.fields[self.to_name]

    def all(self, clear_cache: bool = False) -> Any:
        del clear_cache
        return self._relation_queryset().all()

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self
        return self.__class__(
            instance=instance,
            through=self.through,
            to=self.to,
            owner=self.owner,
            from_foreign_key=self.owner_name,
            to_foreign_key=self.to_name,
            reverse=self.reverse,
            embed_through=self.embed_through,
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

        return attr

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        target = self.resolved_to
        child = target(*args, **kwargs)
        await child.save()
        await self.add(child)
        return child

    async def add_many(self, *children: type["Model"]) -> list[Any]:
        results = []
        for child in children:
            results.append(await self.add(child))
        return results

    async def add(self, child: type["Model"] | dict[str, Any]) -> Any:
        """
        Adds a child to the model as a list

        . Validates the type of the child being added to the relationship and raises error for
        if the type is wrong.
        . Checks if the middle table already contains the record being added. Raises error if yes.
        """
        target = self.resolved_to
        if not isinstance(child, (target, dict)):
            raise RelationshipIncompatible(f"The child is not from the type '{target.__name__}'.")

        if isinstance(child, dict):
            child = target(**child)
            await child.save()

        through = self.resolved_through
        params = self._build_relation_params(child)
        if (
            getattr(self.target_foreign_key, "unique", False)
            and await through.query.filter(**{self.to_name: child}).exists()
        ):
            return None
        if await through.query.filter(**params).exists():
            return None
        relation_instance = through(**params)

        try:
            await relation_instance.save(force_save=True)
        except IntegrityError:
            return None
        return self._bind_embedded_through(child, relation_instance)

    async def remove_many(self, *children: type["Model"]) -> None:
        for child in children:
            await self.remove(child)

    async def remove(self, child: type["Model"] | None = None) -> None:
        """Removes a child from the list of many to many.

        . Validates if there is a relationship between the entities.
        . Removes the field if there is
        """
        target = self.resolved_to
        if child is None:
            if getattr(self.target_foreign_key, "unique", False):
                try:
                    child = await self.get()
                except ObjectNotFound:
                    raise RelationshipNotFound(detail="No child found.") from None
            else:
                raise RelationshipNotFound(detail="No child specified.")

        if not isinstance(child, target):
            raise RelationshipIncompatible(f"The child is not from the type '{target.__name__}'.")

        row_count = await self.resolved_through.query.filter(
            **self._build_relation_params(child)
        ).delete()
        if row_count == 0:
            raise RelationshipNotFound(
                detail=f"There is no relationship between '{self.owner_name}' and '{self.to_name}: {child.pk}'."
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.resolved_through.__name__}"


ManyRelation = Relation
