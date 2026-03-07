from typing import TYPE_CHECKING, Any, cast

from saffier.core.db.context_vars import get_tenant, set_tenant
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

    def __get__(self, _: Any, owner: Any) -> type["QuerySet"]:
        return cast(
            "type[QuerySet]",
            self.__class__(owner=owner, inherit=self.inherit, name=self.name),
        )

    def get_queryset(self) -> "QuerySet":
        """
        Returns the queryset object.

        Checks for a global possible tenant and returns the corresponding queryset.
        """
        if getattr(self.model_class.meta, "abstract", False):
            raise ImproperlyConfigured("Cannot query abstract models.")
        tenant = get_tenant()
        if tenant:
            set_tenant(None)
            return self.queryset_class(
                self.model_class, table=self.model_class.table_schema(tenant)
            )  # type: ignore[arg-type]
        return self.queryset_class(self.model_class)

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

    def __get__(self, _: Any, owner: Any) -> type["QuerySet"]:
        return cast(
            "type[QuerySet]",
            self.__class__(
                redirect_name=self.redirect_name,
                owner=owner,
                inherit=self.inherit,
                name=self.name,
            ),
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == self.name:
            raise AttributeError(name)

        target = getattr(self.model_class, self.redirect_name)
        return getattr(target, name)

    def get_queryset(self) -> "QuerySet":
        return cast("QuerySet", self.__getattr__("get_queryset")())
