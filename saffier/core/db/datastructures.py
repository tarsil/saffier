from dataclasses import dataclass
from typing import ClassVar, List, Optional, Sequence


@dataclass
class Index:
    """
    Class responsible for handling and declaring the database indexes.
    """

    suffix: str = "idx"
    __max_name_length__: ClassVar[int] = 63
    name: Optional[str] = None
    fields: Optional[Sequence[str]] = None

    def __post_init__(self) -> None:
        if self.name is not None and len(self.name) > self.__max_name_length__:
            raise ValueError(
                f"The max length of the index name must be {self.__max_name_length__}. Got {len(self.name)}"
            )

        if not isinstance(self.fields, (tuple, list)):
            raise ValueError("Index.fields must be a list or a tuple.")

        if self.fields and not all(isinstance(field, str) for field in self.fields):
            raise ValueError("Index.fields must contain only strings with field names.")

        if self.name is None:
            self.name = f"{self.suffix}_{'_'.join(self.fields)}"


@dataclass
class UniqueConstraint:
    """
    Class responsible for handling and declaring the database unique_together.
    """

    fields: List[str]
    name: Optional[str] = None
    __max_name_length__: ClassVar[int] = 63

    def __post_init__(self) -> None:
        if self.name is not None and len(self.name) > self.__max_name_length__:
            raise ValueError(
                f"The max length of the constraint name must be {self.__max_name_length__}. Got {len(self.name)}"
            )

        if not isinstance(self.fields, (tuple, list)):
            raise ValueError("UniqueConstraint.fields must be a list or a tuple.")

        if self.fields and not all(isinstance(field, str) for field in self.fields):
            raise ValueError("UniqueConstraint.fields must contain only strings with field names.")
        self.fields = list(self.fields)
