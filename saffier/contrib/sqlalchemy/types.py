from typing import Any


class SubList(list):
    def __init__(self, delimiter: str, *args: Any) -> None:
        self.delimiter = delimiter
        super().__init__(*args)

    def __str__(self) -> str:
        return self.delimiter.join(self)
