import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.exc import IntegrityError

from saffier.core.db import fields
from saffier.exceptions import ObjectNotFound, RelationshipIncompatible, RelationshipNotFound

if TYPE_CHECKING:
    from saffier import Manager, Model, QuerySet, ReflectModel


class RelatedField:
    """
    When a `related_name` is generated, creates a RelatedField from the table pointed
    from the ForeignKey declaration and the the table declaring it.
    """

    def __init__(
        self,
        related_name: str,
        related_to: type["Model"] | type["ReflectModel"],
        related_from: type["Model"] | type["ReflectModel"] | None = None,
        instance: type["Model"] | type["ReflectModel"] | None = None,
        embed_parent: tuple[str, str] | None = None,
        refs: Any = (),
    ) -> None:
        self.related_name = related_name
        self.related_to = related_to
        self.related_from = related_from
        self.instance = instance
        self.embed_parent = embed_parent
        self.refs: list[Any] = []
        if refs:
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes, bytearray)):
                refs = [refs]
            self.stage(*refs)

    @functools.cached_property
    def manager(self) -> "Manager":
        """Returns the manager class"""
        manager = getattr(self.related_from, "query_related", None)
        if manager is None:
            manager = self.related_from.meta.manager  # type: ignore[attr-defined]
        return cast("Manager", manager)

    @functools.cached_property
    def queryset(self) -> "QuerySet":
        return cast("QuerySet", self.manager.get_queryset())

    @functools.cached_property
    def foreign_key(self) -> Any:
        return self.related_from.meta.fields[self.get_foreign_key_field_name()]  # type: ignore[index]

    @property
    def name(self) -> str:
        return self.related_name

    @property
    def is_m2m(self) -> bool:
        return bool(getattr(self.related_from.meta, "is_multi", False))  # type: ignore[union-attr]

    def scoped_queryset(self) -> "QuerySet":
        field = self.get_foreign_key_field_name()
        queryset = cast("QuerySet", self.queryset.filter(**{field: self.instance.pk}))  # type: ignore[arg-type]
        queryset.embed_parent = self.embed_parent

        if self.embed_parent:
            embed_parent_field = self.embed_parent[0].split("__", 1)[0]
            embed_parent_model_field = self.related_from.fields.get(embed_parent_field)  # type: ignore[attr-defined]
            if (
                isinstance(
                    embed_parent_model_field,
                    (fields.ForeignKey, fields.OneToOneField, fields.ManyToManyField),
                )
            ):
                queryset.embed_parent_filters = self.embed_parent
                if embed_parent_field not in queryset._select_related:
                    queryset._select_related.append(embed_parent_field)
            else:
                queryset.embed_parent_filters = None
        else:
            queryset.embed_parent_filters = None

        related = self.m2m_related()
        if related:
            queryset.m2m_related = related[0]
        return queryset

    def m2m_related(self) -> Any:
        """
        Guarantees the the m2m filter is done by the owner of the call
        and not by the children.
        """
        if not self.related_from.meta.is_multi:  # type: ignore
            return

        related = [
            key
            for key, value in self.related_from.fields.items()  # type: ignore
            if key != self.related_to.__name__.lower() and isinstance(value, fields.ForeignKey)
        ]
        return related

    def get_relation(self, **kwargs: Any) -> "RelatedField":
        return self.__class__(
            related_name=self.related_name,
            related_to=self.related_to,
            related_from=self.related_from,
            embed_parent=self.embed_parent,
            **kwargs,
        )

    def to_model(
        self,
        field_name: str,
        value: Any,
        *,
        instance: Any | None = None,
    ) -> dict[str, Any]:
        if isinstance(value, RelatedField):
            return {field_name: value}

        current_instance = self.instance if instance is None else instance
        relation_instance = self.__get__(current_instance, self.related_to)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            value = [value]
        relation_instance.stage(*value)
        return {field_name: relation_instance}

    def __get__(self, instance: Any, owner: Any) -> Any:
        if instance is None:
            return self

        relation = instance.__dict__.get(self.related_name)
        if isinstance(relation, RelatedField) and relation.instance is instance:
            return relation

        relation = self.__class__(
            related_name=self.related_name,
            related_to=self.related_to,
            instance=instance,
            related_from=self.related_from,
            embed_parent=self.embed_parent,
        )
        instance.__dict__[self.related_name] = relation
        return relation

    def __set__(self, instance: Any, value: Any) -> None:
        instance.__dict__[self.related_name] = self.to_model(
            self.related_name,
            value,
            instance=instance,
        )[self.related_name]

    def __getattr__(self, item: Any) -> Any:
        """
        Gets the attribute from the queryset and if it does not
        exist, then lookup in the model.
        """
        if item in {"create", "get_or_create", "update_or_create"}:
            attr = getattr(self.queryset, item)
            return self.wrap_args(attr)

        try:
            return getattr(self.scoped_queryset(), item)
        except AttributeError:
            attr = getattr(self.related_from, item)

        func = self.wrap_args(attr)
        return func

    def get_foreign_key_field_name(self) -> str:
        """
        Table lookup for the given field containing the related field.

        If there is no field with the related_name declared, find the first field
        with the FK to the related_to.
        """
        for field, value in self.related_from.fields.items():  # type: ignore
            if isinstance(value, (fields.ForeignKey, fields.OneToOneField)) and (
                value.related_name == self.related_name
            ):
                return field

        field_name: str | None = None
        for field, value in self.related_from.fields.items():  # type: ignore
            if isinstance(value, (fields.ForeignKey, fields.OneToOneField)) and (
                not value.related_name or value.related_name is None
            ):
                field_name = field
                break
        return cast("str", field_name)

    def traverse_field(self, path: str) -> tuple[Any, str, str]:
        return (
            self.related_from,
            self.get_foreign_key_field_name(),
            path.removeprefix(self.related_name).removeprefix("__"),
        )

    def is_cross_db(self, owner_database: Any | None = None) -> bool:
        if owner_database is None:
            owner_database = getattr(self.related_to, "database", None)
            if owner_database is None:
                owner_registry = getattr(getattr(self.related_to, "meta", None), "registry", None)
                owner_database = getattr(owner_registry, "database", None)
        target_database = getattr(self.foreign_key.owner, "database", None)
        if target_database is None:
            target_registry = getattr(getattr(self.foreign_key.owner, "meta", None), "registry", None)
            target_database = getattr(target_registry, "database", None)
        if owner_database is None or target_database is None:
            return False
        return str(owner_database.url) != str(target_database.url)

    def get_related_model_for_admin(self) -> Any | None:
        registry = getattr(getattr(self.related_from, "meta", None), "registry", None)
        admin_models = getattr(registry, "admin_models", ())
        if registry and self.related_from.__name__ in admin_models:
            return self.related_from
        return None

    def wrap_args(self, func: Any) -> Any:
        @functools.wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            field = self.get_foreign_key_field_name()
            kwargs[field] = self.instance.pk  # type: ignore
            return func(*args, **kwargs)

        return wrapped

    def stage(self, *children: Any) -> None:
        for child in children:
            if self.is_m2m:
                related_names = self.m2m_related() or []
                if not related_names:
                    raise RelationshipIncompatible("No related target found for many-to-many.")
                other_field = related_names[0]
                other_model = self.related_from.fields[other_field].target  # type: ignore[index]
                if not isinstance(child, (other_model, dict)):
                    raise RelationshipIncompatible(
                        f"The child is not from the type '{other_model.__name__}'."
                    )
                self.refs.append(child)
                continue

            if not isinstance(child, (self.related_from, dict)):
                raise RelationshipIncompatible(
                    f"The child is not from the type '{self.related_from.__name__}'."
                )
            self.refs.append(child)

    async def save_related(self) -> None:
        while self.refs:
            await self.add(self.refs.pop(0))

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        if self.is_m2m:
            related_names = self.m2m_related() or []
            if not related_names:
                raise RelationshipIncompatible("No related target found for many-to-many.")
            other_field = related_names[0]
            other_model = self.related_from.fields[other_field].target  # type: ignore[index]
            child = other_model(*args, **kwargs)
            await child.save()
            await self.add(child)
            return child

        kwargs[self.get_foreign_key_field_name()] = self.instance
        return await self.queryset.create(*args, **kwargs)

    async def add_many(self, *children: Any) -> list[Any]:
        results = []
        for child in children:
            results.append(await self.add(child))
        return results

    async def add(self, child: Any) -> Any:
        if self.is_m2m:
            related_names = self.m2m_related() or []
            if not related_names:
                raise RelationshipIncompatible("No related target found for many-to-many.")
            other_field = related_names[0]
            other_model = self.related_from.fields[other_field].target  # type: ignore[index]
            if not isinstance(child, (other_model, dict)):
                raise RelationshipIncompatible(
                    f"The child is not from the type '{other_model.__name__}'."
                )
            if isinstance(child, dict):
                child = other_model(**child)
                await child.save()

            payload = {
                self.get_foreign_key_field_name(): self.instance,
                other_field: child,
            }
            if getattr(self.foreign_key, "unique", False) and await self.related_from.query.filter(
                **{self.get_foreign_key_field_name(): self.instance}
            ).exists():
                return None
            if await self.related_from.query.filter(**payload).exists():
                return None
            try:
                through_instance = await self.related_from.query.create(**payload)
            except IntegrityError:
                return None

            if self.embed_parent and self.embed_parent[1]:
                setattr(child, self.embed_parent[1], through_instance)
            return child

        if not isinstance(child, (self.related_from, dict)):
            raise RelationshipIncompatible(
                f"The child is not from the type '{self.related_from.__name__}'."
            )

        if isinstance(child, dict):
            child = self.related_from(**child)

        setattr(child, self.get_foreign_key_field_name(), self.instance)
        try:
            await child.save()
        except IntegrityError:
            return None
        return child

    async def remove_many(self, *children: Any) -> None:
        for child in children:
            await self.remove(child)

    async def remove(self, child: Any | None = None) -> None:
        foreign_key = self.foreign_key
        if child is None:
            if getattr(foreign_key, "unique", False):
                try:
                    child = await self.get()
                except ObjectNotFound:
                    raise RelationshipNotFound(detail="No child found.") from None
            else:
                raise RelationshipNotFound(detail="No child specified.")

        if self.is_m2m:
            related_names = self.m2m_related() or []
            if not related_names:
                raise RelationshipNotFound(detail="No related target found for many-to-many.")
            other_field = related_names[0]
            other_model = self.related_from.fields[other_field].target  # type: ignore[index]
            if not isinstance(child, other_model):
                raise RelationshipIncompatible(
                    f"The child is not from the type '{other_model.__name__}'."
                )

            row_count = await self.related_from.query.filter(
                **{
                    self.get_foreign_key_field_name(): self.instance,
                    other_field: child,
                }
            ).delete()
            if row_count == 0:
                raise RelationshipNotFound(
                    detail=(
                        f"There is no relationship between '{self.get_foreign_key_field_name()}' "
                        f"and '{other_field}: {child.pk}'."
                    )
                )
            return

        if not isinstance(child, self.related_from):
            raise RelationshipIncompatible(
                f"The child is not from the type '{self.related_from.__name__}'."
            )

        setattr(child, self.get_foreign_key_field_name(), None)
        await child.save()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"({self.related_to.__name__}={self.related_name})"
