"""Manager descriptors used to bind query behavior to Saffier models."""

import copy
from typing import TYPE_CHECKING, Any, cast

from saffier.core.db.context_vars import get_schema, get_tenant, set_tenant
from saffier.core.db.querysets.base import QuerySet
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    pass


class BaseManager:
    """Base descriptor for model-bound queryset factories."""

    queryset_class = QuerySet

    def __init__(
        self,
        model_class: Any = None,
        *,
        owner: Any = None,
        inherit: bool = True,
        name: str = "",
        instance: Any = None,
    ) -> None:
        self.owner = owner if owner is not None else model_class
        self.inherit = inherit
        self.name = name
        self.instance = instance

    @property
    def model_class(self) -> Any:
        return self.owner

    @model_class.setter
    def model_class(self, value: Any) -> None:
        self.owner = value

    def get_queryset(self) -> "QuerySet":
        raise NotImplementedError(
            f"The {self!r} manager doesn't implement the get_queryset method."
        )


class Manager(BaseManager):
    """Default manager descriptor for Saffier models.

    A manager is both a descriptor and a queryset factory. Accessing it on a
    model class returns a class-bound manager; accessing it on an instance
    returns a shallow copy bound to that instance so schema and database context
    can follow the instance.

    Examples:
        class PublishedManager(saffier.Manager):
            def get_queryset(self) -> saffier.QuerySet:
                return super().get_queryset().filter(is_published=True)
    """

    def __get__(self, instance: Any, owner: Any) -> Any:
        self.owner = owner
        if instance is None:
            self.instance = None
            return self

        cached = instance.__dict__.get(self.name)
        if cached is not None:
            return cached

        manager = copy.copy(self)
        manager.owner = owner
        manager.instance = instance
        instance.__dict__[self.name] = manager
        return manager

    def get_queryset(self) -> "QuerySet":
        """Build a queryset bound to the current model, instance, and schema context.

        Returns:
            QuerySet: Queryset configured for the active model, schema, and
            database context.

        Raises:
            ImproperlyConfigured: If the manager is used on an abstract model.
        """
        if getattr(self.model_class.meta, "abstract", False):
            raise ImproperlyConfigured("Cannot query abstract models.")
        schema = None
        database = getattr(self.model_class, "database", None)

        if self.instance is not None:
            if hasattr(self.instance, "get_active_instance_schema"):
                schema = self.instance.get_active_instance_schema()
            else:
                schema = getattr(self.instance, "__using_schema__", None)
            database = getattr(self.instance, "database", database)
        else:
            if hasattr(self.model_class, "get_active_class_schema"):
                schema = self.model_class.get_active_class_schema()
            else:
                schema = getattr(self.model_class, "__using_schema__", None)

        if schema is None:
            tenant = get_tenant()
            if tenant:
                set_tenant(None)
                schema = tenant
            else:
                schema = get_schema()

        if schema is not None:
            return self.queryset_class(
                self.model_class,
                using_schema=schema,
                table=self.model_class.table_schema(schema),
                database=database,
            )  # type: ignore[arg-type]

        return self.queryset_class(self.model_class, database=database)

    def __getattr__(self, item: Any) -> Any:
        """
        Gets the attribute from the queryset and if it does not
        exist, then lookup in the model.
        """
        if str(item).startswith("_") or item == self.name:
            raise AttributeError(item)
        try:
            return getattr(self.get_queryset(), item)
        except AttributeError:
            return getattr(self.model_class, item)


class RedirectManager(Manager):
    """Manager proxy that forwards operations to another manager attribute.

    Redirect managers are used for aliases such as `query_related`, where the
    framework wants a second manager name with the same underlying queryset
    behavior as another manager on the model.
    """

    def __init__(self, *, redirect_name: str, **kwargs: Any) -> None:
        self.redirect_name = redirect_name
        super().__init__(**kwargs)

    def __get__(self, instance: Any, owner: Any) -> Any:
        self.owner = owner
        if instance is None:
            self.instance = None
            return self

        cached = instance.__dict__.get(self.name)
        if cached is not None:
            return cached

        manager = copy.copy(self)
        manager.owner = owner
        manager.instance = instance
        instance.__dict__[self.name] = manager
        return manager

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == self.name:
            raise AttributeError(name)

        target = getattr(self.model_class, self.redirect_name)
        return getattr(target, name)

    def get_queryset(self) -> "QuerySet":
        return cast("QuerySet", self.__getattr__("get_queryset")())
