from typing import Annotated

from sayer import Argument, command

from saffier.cli.base import downgrade as _downgrade
from saffier.cli.common_params import DirectoryOption, ExtraArgOption, SQLOption, TagOption
from saffier.cli.state import get_migration_app


@command(context_settings={"ignore_unknown_options": True})
def downgrade(
    sql: SQLOption,
    tag: TagOption,
    arg: ExtraArgOption,
    revision: Annotated[str, Argument("-1")],
    directory: DirectoryOption,
) -> None:
    """Revert to a previous version"""
    _downgrade(get_migration_app(), directory, revision, sql, tag, arg)
