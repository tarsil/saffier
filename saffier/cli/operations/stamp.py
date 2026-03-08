from sayer import command

from saffier.cli.base import stamp as _stamp
from saffier.cli.common_params import DirectoryOption, RevisionHeadArgument, SQLOption, TagOption
from saffier.cli.state import get_migration_app


@command
def stamp(
    sql: SQLOption, tag: TagOption, revision: RevisionHeadArgument, directory: DirectoryOption
) -> None:
    """'stamp' the revision table with the given revision; don't run any
    migrations"""
    _stamp(get_migration_app(), directory, revision, sql, tag)
