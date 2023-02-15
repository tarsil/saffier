import typing

if typing.TYPE_CHECKING:
    from saffier.models import Model

# Create a var type for the Saffier Model
SaffierModel = typing.TypeVar("SaffierModel", bound="Model")
C = typing.TypeVar("C", covariant=True)


class QuerySetSingle(typing.Protocol[C]):
    """
    Base Protocol for a single instance of the Saffier Model.
    """

    # pylint: disable=W0104
    def __await__(self) -> typing.Generator[typing.Any, None, C]:
        ...  # pragma: nocoverage

    # def prefetch_related(self, *args: typing.Union[str, Prefetch]) -> "QuerySetSingle[T_co]":
    #     ...  # pragma: nocoverage

    def select_related(self, *args: str) -> "QuerySetSingle[C]":
        ...  # pragma: nocoverage

    # def annotate(self, **kwargs: typing.Function) -> "QuerySetSingle[T_co]":
    #     ...  # pragma: nocoverage

    # def only(self, *fields_for_select: str) -> "QuerySetSingle[T_co]":
    #     ...  # pragma: nocoverage

    # def values_list(self, *fields_: str, flat: bool = False) -> "ValuesListQuery[Literal[True]]":
    #     ...  # pragma: nocoverage

    # def values(self, *args: str, **kwargs: str) -> "ValuesQuery[Literal[True]]":
    #     ...  # pragma: nocoverage


class AwaitableQuery(typing.Generic[SaffierModel]):
    __slots__ = ("model_class",)

    def __init__(self, model_class: typing.Type[SaffierModel]) -> None:
        self.model_class: typing.Type[SaffierModel] = model_class

    def _make_query(self):
        raise NotImplementedError()  # pragma: no cover

    def _execute(self) -> typing.Any:
        raise NotImplementedError()
