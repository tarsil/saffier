import sys
from functools import wraps

from alembic.util import CommandError
from loguru import logger


def catch_errors(fn):
    @wraps(fn)
    def wrap(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except (CommandError, RuntimeError) as exc:
            logger.error(f"Error: {str(exc)}")
            sys.exit(1)

    return wrap
