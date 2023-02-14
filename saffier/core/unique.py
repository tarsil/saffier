import typing

from saffier.types import Empty, HashableType


class Uniqueness:
    """
    A set-like class that tests for uniqueness of primitive types.
    Ensures the `True` and `False` are treated as distinct from `1` and `0`,
    and coerces non-hashable instances that cannot be added to sets,
    into hashable representations that can.
    """

    TRUE = Empty()
    FALSE = Empty()
    HASHABLE_TYPES = (int, bool, str, float, list, dict)

    def __init__(self, items: list = None) -> None:
        self._set: set = set()
        for item in items or []:
            self.add(item)

    def __contains__(self, item: typing.Any) -> bool:
        item = self.make_hashable(item)
        return item in self._set

    def add(self, item: typing.Any) -> None:
        item = self.make_hashable(item)
        self._set.add(item)

    def make_hashable(self, element: typing.Any) -> typing.Any:
        """
        Coerce a primitive into a uniquely hashable type, for uniqueness checks.
        """
        assert (element is None) or isinstance(element, HashableType)

        if element is True:
            return self.TRUE
        elif element is False:
            return self.FALSE
        elif isinstance(element, list):
            return ("list", tuple([self.make_hashable(item) for item in element]))
        elif isinstance(element, dict):
            return (
                "dict",
                tuple(
                    [
                        (self.make_hashable(key), self.make_hashable(value))
                        for key, value in element.items()
                    ]
                ),
            )
        return element
