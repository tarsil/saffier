from sayer import command

from saffier.cli.base import edit as _edit
from saffier.cli.common_params import DirectoryOption, RevisionHeadArgument
from saffier.cli.state import get_migration_app


@command
def edit(revision: RevisionHeadArgument, directory: DirectoryOption) -> None:
    """Edit a revision file"""
    _edit(get_migration_app(), directory, revision)
