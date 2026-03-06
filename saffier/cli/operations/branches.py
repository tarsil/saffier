"""
Client to interact with Saffier models and migrations.
"""

from sayer import command

from saffier.cli.base import branches as _branches
from saffier.cli.common_params import DirectoryOption, VerboseOption
from saffier.cli.state import get_migration_app


@command
def branches(verbose: VerboseOption, directory: DirectoryOption) -> None:
    """Show current branch points"""
    _branches(get_migration_app(), directory, verbose)
