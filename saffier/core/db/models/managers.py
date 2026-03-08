import copy
from typing import TYPE_CHECKING, Any, cast

from saffier.core.db.context_vars import get_schema, get_tenant, set_tenant
from saffier.core.db.querysets.base import QuerySet
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    pass


class BaseManager:
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
    """
    Base Manager for the Saffier Models.
    To create a custom manager, the best approach is to inherit from the ModelManager.

    Example:
        from saffier.managers import ModelManager
        from saffier.core.db.models import Model


        class MyCustomManager(ModelManager):
            ...


        class MyOtherManager(ModelManager):
            ...


        class MyModel(saffier.Model):
            query = MyCustomManager()
            active = MyOtherManager()

            ...
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
        """
        Returns the queryset object.

        Checks for a global possible tenant and returns the corresponding queryset.
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
