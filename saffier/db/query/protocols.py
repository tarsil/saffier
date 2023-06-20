import typing

if typing.TYPE_CHECKING:
    from saffier.db.models.base import Model

# Create a var type for the Saffier Model
SaffierModel = typing.TypeVar("SaffierModel", bound="Model")


class AwaitableQuery(typing.Generic[SaffierModel]):
    __slots__ = ("model_class",)

    def __init__(self, model_class: typing.Type[SaffierModel]) -> None:
        self.model_class: typing.Type[SaffierModel] = model_class

    async def _execute(self) -> typing.Any:
        raise NotImplementedError()
