from typing import TYPE_CHECKING, Any, Dict, Tuple, Type, Union, cast

from pydantic import ConfigDict

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.db.models.metaclasses import MetaInfo


class ProxyModel:
    """
    When a model needs to be mirrored without affecting the
    original, this instance is triggered instead.
    """

    def __init__(
        self,
        name: str,
        module: str,
        *,
        bases: Union[Tuple[Type["Model"]], None] = None,
        definitions: Union[Dict[Any, Any], None] = None,
        metadata: Union[Type["MetaInfo"], None] = None,
        qualname: Union[str, None] = None,
        config: Union[ConfigDict, None] = None,
        proxy: bool = True,
        pydantic_extra: Union[Any, None] = None,
    ) -> None:
        self.__name__: str = name
        self.__module__: str = module
        self.__bases__: Union[Tuple[Type["Model"]], None] = bases
        self.__definitions__: Union[Dict[Any, Any], None] = definitions
        self.__metadata__: Union[Type["MetaInfo"], None] = metadata
        self.__qualname__: Union[str, None] = qualname
        self.__config__: Union[ConfigDict, None] = config
        self.__proxy__: bool = proxy
        self.__pydantic_extra__ = pydantic_extra
        self.__model__ = None

    def build(self) -> "ProxyModel":
        """
        Generates the model proxy for the __model__ definition.
        """
        from saffier.core.utils.models import create_saffier_model

        model: Type["Model"] = create_saffier_model(
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
    def model(self) -> Type["Model"]:
        return cast("Type[Model]", self.__model__)

    @model.setter
    def model(self, value: Type["Model"]) -> None:
        self.__model__ = value  # type: ignore

    def __repr__(self) -> str:
        name = f"Proxy{self.__name__}"
        return f"<{name}: [{self.__definitions__}]"
