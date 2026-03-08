from sayer import command

from saffier.cli.base import check as _check
from saffier.cli.common_params import DirectoryOption
from saffier.cli.state import get_migration_app


@command
def check(directory: DirectoryOption) -> None:
    """Check whether current models would produce new migration operations.

    It exits through the shared migration helper logic.
    """
    _check(get_migration_app(), directory)
