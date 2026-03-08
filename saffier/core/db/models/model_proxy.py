from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.db.models.metaclasses import MetaInfo


class ProxyModel:
    """Builder object used to generate detached proxy models.

    Proxy models mirror a concrete model's fields and metadata without
    registering themselves as first-class runtime models.
    """

    def __init__(
        self,
        name: str,
        module: str,
        *,
        bases: tuple[type["Model"]] | None = None,
        definitions: dict[Any, Any] | None = None,
        metadata: type["MetaInfo"] | None = None,
        qualname: str | None = None,
        config: dict[str, Any] | None = None,
        proxy: bool = True,
        model_extra: Any | None = None,
    ) -> None:
        self.__name__: str = name
        self.__module__: str = module
        self.__bases__: tuple[type[Model]] | None = bases
        self.__definitions__: dict[Any, Any] | None = definitions
        self.__metadata__: type[MetaInfo] | None = metadata
        self.__qualname__: str | None = qualname
        self.__config__: dict[str, Any] | None = config
        self.__proxy__: bool = proxy
        self.__model_extra__ = model_extra
        self.__model__ = None

    def build(self) -> "ProxyModel":
        """Generate and attach the proxy model class described by this builder.

        Returns:
            ProxyModel: The current builder with `model` populated.
        """
        from saffier.core.utils.models import create_saffier_model

        model: type[Model] = create_saffier_model(
            __name__=self.__name__,
            __module__=self.__module__,
            __bases__=self.__bases__,
            __definitions__=self.__definitions__,
            __metadata__=self.__metadata__,
            __qualname__=self.__qualname__,
            __proxy__=self.__proxy__,
        )
        self.__model__ = model  # type: ignore
        return self

    @property
    def model(self) -> type["Model"]:
        return cast("type[Model]", self.__model__)

    @model.setter
    def model(self, value: type["Model"]) -> None:
        self.__model__ = value  # type: ignore

    def __repr__(self) -> str:
        name = f"Proxy{self.__name__}"
        return f"<{name}: [{self.__definitions__}]"
