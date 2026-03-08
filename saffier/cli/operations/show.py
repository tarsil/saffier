from sayer import command

from saffier.cli.base import show as _show
from saffier.cli.common_params import DirectoryOption, RevisionHeadArgument
from saffier.cli.state import get_migration_app


@command
def show(revision: RevisionHeadArgument, directory: DirectoryOption) -> None:
    """Show details for one migration revision."""
    _show(get_migration_app(), directory, revision)
