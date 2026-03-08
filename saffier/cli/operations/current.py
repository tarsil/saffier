from sayer import command

from saffier.cli.base import current as _current
from saffier.cli.common_params import DirectoryOption, VerboseOption
from saffier.cli.state import get_migration_app


@command
def current(verbose: VerboseOption, directory: DirectoryOption) -> None:
    """Display the current revision for each database."""
    _current(get_migration_app(), directory, verbose)
