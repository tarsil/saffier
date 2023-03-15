import sys
from functools import wraps
from typing import Any, Callable

from alembic.util import CommandError
from loguru import logger

from saffier.types import DictAny


def catch_errors(fn: Callable) -> Any:
    @wraps(fn)
    def wrap(*args: Any, **kwargs: DictAny) -> Any:
        try:
            fn(*args, **kwargs)
        except (CommandError, RuntimeError) as exc:
            logger.error(f"Error: {str(exc)}")
            sys.exit(1)

    return wrap
