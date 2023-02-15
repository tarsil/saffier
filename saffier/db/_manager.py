import inspect
import typing
from functools import wraps

import sqlalchemy

from saffier.db.queryset import QuerySet
from saffier.types import DictAny


class BaseManager:
    """
    The base of all managers from Saffier.

    This will make sure that a queryset object is returned in a simple fashion
    and the database operations can be performed normally on the top of the SQLAlchemy core.
    """

    def __new__(cls, *args, **kwargs: DictAny) -> typing.Any:
        _object = super().__new__(cls)
        _object._constructor_args = (args, kwargs)
        return _object

    def __init__(self, model_class=None) -> None:
        super().__init__()
        self.model_class = None
        self.name = None
        self._filter_clauses = {}

    def __str__(self) -> str:
        return " %s.%s" % (self.model_class.__name__, self.name)

    @classmethod
    def _get_queryset_methods(cls, queryset_class: typing.Type[QuerySet]) -> None:
        def create_method(name: str, method: typing.Any):
            @wraps(method)
            def manager_method(self, *args, **kwargs):
                return getattr(self.get_queryset(), name)(*args, **kwargs)

            return manager_method

        methods = {}
        for name, method in inspect.getmembers(queryset_class, predicate=inspect.isfunction):
            if hasattr(cls, name):
                continue
            if name.startswith("_"):
                continue
            methods[name] = create_method(name, method)
        return methods

    @classmethod
    def from_queryset(
        cls, queryset_class: typing.Type[QuerySet], class_name: typing.Optional[str] = None
    ) -> typing.Any:
        if class_name is None:
            class_name = "%sFrom%s" % (cls.__name__, queryset_class.__name__)

        queryset = type(
            class_name,
            (cls,),
            {"_queryset_class": queryset_class, **cls._get_queryset_methods(queryset_class)},
        )
        return queryset

    def __class_getitem__(cls, *args, **kwargs):
        return cls

    async def get_queryset(self):
        """
        Return a new QuerySet object. Subclasses can override this method to
        customize the behavior of the Manager.
        """
        return self._queryset_class(
            model_class=self.model_class,
            filter_clauses=self._filter_clauses,
        )

    async def all(self):
        queryset = await self.get_queryset()
        return queryset

    def __eq__(self, __o: typing.Type["BaseManager"]) -> bool:
        return isinstance(__o, self.__class__) and self._constructor_args == __o._constructor_args

    def __hash__(self) -> int:
        return id(self)

    @property
    def database(self):
        return self._queryset_class.database

    @property
    def table(self) -> sqlalchemy.Table:
        return self._queryset_class.model_class.table

    @property
    def pkname(self):
        return self._queryset_class.model_class.pkname


class Manager(BaseManager.from_queryset(QuerySet)):
    ...
