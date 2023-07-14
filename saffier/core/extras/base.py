from abc import ABC, abstractmethod
from typing import Any


class BaseExtra(ABC):
    @abstractmethod
    def set_saffier_extension(self, app: Any) -> None:
        raise NotImplementedError(
            "Any class implementing the extra must implement set_saffier_extension() ."
        )
