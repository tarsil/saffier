from typing import Any, Iterator, List, Union

from pydantic import BaseConfig, BaseModel, ValidationError

from saffier.core.datastructures import ArbitraryHashableBaseModel as SaffierBaseModel
from saffier.types import DictAny


class Position(SaffierBaseModel):
    def __init__(self, line_no: int, column_no: int, char_index: int, **kwargs: DictAny):
        super().__init__(**kwargs)
        self.line_no = line_no
        self.column_no = column_no
        self.char_index = char_index

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Position)
            and self.line_no == other.line_no
            and self.column_no == other.column_no
            and self.char_index == other.char_index
        )

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return (
            f"{class_name}(line_no={self.line_no}, column_no={self.column_no},"
            f" char_index={self.char_index})"
        )


class Message(SaffierBaseModel):
    """
    An individual error message, within a ValidationError.
    """

    def __init__(
        self,
        *,
        text: str,
        code: str = None,
        key: Union[int, str] = None,
        index: List[Union[int, str]] = None,
        position: Position = None,
        start_position: Position = None,
        end_position: Position = None,
        **kwargs: DictAny,
    ):
        """
        text - The error message. 'May not have more than 100 characters'
        code - An optional error code, eg. 'max_length'
        key - An optional key of the message within a single parent. eg. 'username'
        index - The index of the message
            within a nested object. eg. ['users', 3, 'username']

        Optionally either:

        position - The start and end position of the error message
            within the raw content.

        Or:

        start_position - The start position of the error message within the raw content.
        end_position - The end position of the error message within the raw content.
        """
        super().__init__(**kwargs)
        self.text = text
        self.code = "custom" if code is None else code
        if key is not None:
            assert index is None
            self.index = [key]
        else:
            self.index = [] if index is None else index

        if position is None:
            self.start_position = start_position
            self.end_position = end_position
        else:
            assert start_position is None
            assert end_position is None
            self.start_position = position
            self.end_position = position

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Message) and (
            self.text == other.text
            and self.code == other.code
            and self.index == other.index
            and self.start_position == other.start_position
            and self.end_position == other.end_position
        )

    def __hash__(self) -> int:
        ident = (self.code, tuple(self.index))
        return hash(ident)

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        index_str = f", index={self.index!r}" if self.index else ""
        if self.start_position is None:
            position_str = ""
        elif self.start_position == self.end_position:
            position_str = f", position={self.start_position!r}"
        else:
            position_str = (
                f", start_position={self.start_position!r}," f" end_position={self.end_position!r}"
            )
        return f"{class_name}(text={self.text!r}," f" code={self.code!r}{index_str}{position_str})"


class ValidationResult(SaffierBaseModel):
    """
    A pair providing the validated data or validation error.
    Typically unpacked like so:

    value, error = MySchema.validate_or_error(data)
    """

    def __init__(
        self, *, value: Any = None, error: ValidationError = None, **kwargs: DictAny
    ) -> None:
        """
        Either:

        value - The validated data.

        Or:

        error - The validation error.
        """
        super().__init__(**kwargs)
        assert value is None or error is None
        self.value = value
        self.error = error

    def __iter__(self) -> Iterator:
        yield self.value
        yield self.error

    def __bool__(self) -> bool:
        return self.error is None

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        if self.error is not None:
            return f"{class_name}(error={self.error!r})"
        return f"{class_name}(value={self.value!r})"
