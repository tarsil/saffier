from sayer import command

from saffier.cli.base import upgrade as _upgrade
from saffier.cli.common_params import (
    DirectoryOption,
    ExtraArgOption,
    RevisionHeadArgument,
    SQLOption,
    TagOption,
)
from saffier.cli.state import get_migration_app


@command(context_settings={"ignore_unknown_options": True})
def migrate(
    sql: SQLOption,
    tag: TagOption,
    arg: ExtraArgOption,
    revision: RevisionHeadArgument,
    directory: DirectoryOption,
) -> None:
    """
    Upgrades to the latest version or to a specific version
    provided by the --tag.
    """
    _upgrade(get_migration_app(), directory, revision, sql, tag, arg)
