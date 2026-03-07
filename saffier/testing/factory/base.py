from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from saffier.core.utils.sync import run_sync
from saffier.testing.exceptions import ExcludeValue

from .context_vars import model_factory_context
from .fields import FactoryField
from .metaclasses import ModelFactoryMeta

if TYPE_CHECKING:
    from saffier.core.connection.database import Database
    from saffier.core.db.models.model import Model

    from .metaclasses import MetaInfo
    from .types import FieldFactoryCallback, ModelFactoryContext


DEFAULTS_WITH_SAVE = frozenset(["self", "class", "__class__", "kwargs", "save"])


class ModelFactoryContextImplementation(dict):
    def __getattr__(self, name: str) -> Any:
        return getattr(self["faker"], name)

    def copy(self) -> ModelFactoryContextImplementation:
        return ModelFactoryContextImplementation(self)


class ModelFactory(metaclass=ModelFactoryMeta):
    meta: ClassVar[MetaInfo]
    exclude_autoincrement: ClassVar[bool] = True
    __defaults__: ClassVar[dict[str, Any]] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.__kwargs__ = kwargs
        for key, value in self.__defaults__.items():
            self.__kwargs__.setdefault(key, value)

    @property
    def saffier_fields(self) -> dict[str, Any]:
        return self.meta.model.meta.fields

    def to_factory_field(self) -> FactoryField:
        return FactoryField(callback=lambda field, context, k: self.build(**k))

    def to_list_factory_field(self, *, min: int = 0, max: int = 10) -> FactoryField:
        def callback(field: FactoryField, context: ModelFactoryContext, k: dict[str, Any]) -> Any:
            min_value = k.pop("min", min)
            max_value = k.pop("max", max)
            return [
                self.build(**k)
                for _ in range(context["faker"].random_int(min=min_value, max=max_value))
            ]

        return FactoryField(callback=callback)

    def build_values(
        self,
        *,
        faker: Any | None = None,
        parameters: dict[str, dict[str, Any] | FieldFactoryCallback] | None = None,
        overwrites: dict[str, Any] | None = None,
        exclude: Collection[str] = (),
        exclude_autoincrement: bool | None = None,
        callcounts: dict[int, int] | None = None,
    ) -> dict[str, Any]:
        context = model_factory_context.get(None)

        if callcounts is None:
            callcounts = context["callcounts"] if context else self.meta.callcounts
        if faker is None:
            faker = context["faker"] if context else self.meta.faker
        if not parameters:
            parameters = {}
        if not overwrites:
            overwrites = {}

        if exclude_autoincrement is None:
            exclude_autoincrement = (
                context["exclude_autoincrement"] if context else self.exclude_autoincrement
            )
        if exclude_autoincrement:
            for field_name, db_field in self.meta.model.meta.fields.items():
                if getattr(db_field, "autoincrement", False):
                    exclude = {*exclude, field_name}

        kwargs = self.__kwargs__.copy()
        kwargs.update(overwrites)
        values: dict[str, Any] = {}

        if context is None:
            context = cast(
                "ModelFactoryContext",
                ModelFactoryContextImplementation(
                    faker=faker,
                    exclude_autoincrement=bool(exclude_autoincrement),
                    depth=0,
                    callcounts=callcounts,
                ),
            )
            token = model_factory_context.set(context)
        else:
            context = context.copy()
            context["depth"] += 1
            token = model_factory_context.set(context)

        try:
            for name, field in self.meta.fields.items():
                if name in kwargs or name in exclude or field.exclude:
                    continue

                current_parameters_or_callback = parameters.get(name)

                if isinstance(current_parameters_or_callback, str):
                    callback_name = current_parameters_or_callback

                    def _faker_callback(
                        field: FactoryField,
                        context: ModelFactoryContext,
                        params: dict[str, Any],
                        _callback_name: str = callback_name,
                    ) -> Any:
                        return getattr(context["faker"], _callback_name)(**params)

                    current_parameters_or_callback = _faker_callback

                try:
                    if callable(current_parameters_or_callback):
                        params = field.get_parameters(context=context)
                        randomly_unset = params.pop("randomly_unset", None)
                        if randomly_unset is not None and randomly_unset is not False:
                            if randomly_unset is True:
                                randomly_unset = 50
                            if faker.pybool(randomly_unset):
                                raise ExcludeValue

                        randomly_nullify = params.pop("randomly_nullify", None)
                        if randomly_nullify is not None and randomly_nullify is not False:
                            if randomly_nullify is True:
                                randomly_nullify = 50
                            if faker.pybool(randomly_nullify):
                                values[name] = None
                                continue

                        field.inc_callcount()
                        values[name] = current_parameters_or_callback(field, context, params)
                    else:
                        params = field.get_parameters(
                            context=context,
                            parameters=cast(dict[str, Any], current_parameters_or_callback),
                        )
                        randomly_unset = params.pop("randomly_unset", None)
                        if randomly_unset is not None and randomly_unset is not False:
                            if randomly_unset is True:
                                randomly_unset = 50
                            if faker.pybool(randomly_unset):
                                raise ExcludeValue

                        randomly_nullify = params.pop("randomly_nullify", None)
                        if randomly_nullify is not None and randomly_nullify is not False:
                            if randomly_nullify is True:
                                randomly_nullify = 50
                            if faker.pybool(randomly_nullify):
                                values[name] = None
                                continue
                        field.inc_callcount()
                        values[name] = field(context=context, parameters=params)
                except ExcludeValue:
                    ...
            values.update(kwargs)
        finally:
            model_factory_context.reset(token)

        return values

    def build(
        self,
        *,
        faker: Any | None = None,
        parameters: dict[str, dict[str, Any] | FieldFactoryCallback] | None = None,
        overwrites: dict[str, Any] | None = None,
        exclude: Collection[str] = (),
        exclude_autoincrement: bool | None = None,
        database: Database | None | Literal[False] = None,
        schema: str | None | Literal[False] = None,
        save: bool = False,
        callcounts: dict[int, int] | None = None,
    ) -> Model:
        if save:
            kwargs = {k: v for k, v in locals().items() if k not in DEFAULTS_WITH_SAVE}
            return cast("Model", run_sync(self.build_and_save(**kwargs)))

        if database is None:
            database = getattr(self, "database", None)
        elif database is False:
            database = None

        if schema is None:
            schema = getattr(self, "schema", None)
        elif schema is False:
            schema = None

        values = self.build_values(
            faker=faker,
            parameters=parameters,
            overwrites=overwrites,
            exclude=exclude,
            exclude_autoincrement=exclude_autoincrement,
            callcounts=callcounts,
        )
        result = self.meta.model(**values)
        result._db_loaded = True
        if database is not None:
            result.database = database  # type: ignore
        if schema is not None:
            result.__using_schema__ = schema
        return result

    async def build_and_save(
        self,
        *,
        faker: Any | None = None,
        parameters: dict[str, dict[str, Any] | FieldFactoryCallback] | None = None,
        overwrites: dict[str, Any] | None = None,
        exclude: Collection[str] = (),
        exclude_autoincrement: bool | None = None,
        database: Database | None | Literal[False] = None,
        schema: str | None | Literal[False] = None,
        callcounts: dict[int, int] | None = None,
    ) -> Model:
        kwargs = {k: v for k, v in locals().items() if k not in DEFAULTS_WITH_SAVE}
        model_instance = self.build(**kwargs, save=False)
        return await model_instance.save()
