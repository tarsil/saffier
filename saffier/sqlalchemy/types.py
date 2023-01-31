from saffier.types import DictAny


class SubList(list):
    def __init__(self, delimiter: str, *args: DictAny) -> None:
        self.delimiter = delimiter
        super().__init__(*args)

    def __str__(self):
        return self.delimiter.join(self)
