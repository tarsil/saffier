import logging
import sys
from functools import wraps
from typing import Any, TypeVar

from alembic.util import CommandError

T = TypeVar("T")
logger = logging.getLogger(__name__)


def catch_errors(fn: T) -> T:
    @wraps(fn)  # type: ignore
    def wrap(*args: Any, **kwargs: Any) -> T:
        try:
            fn(*args, **kwargs)  # type: ignore
        except (CommandError, RuntimeError) as exc:
            logger.error(f"Error: {str(exc)}")
            sys.exit(1)

    return wrap  # type: ignore
