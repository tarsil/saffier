from typing import Annotated

from sayer import Argument, Option, command

from saffier.cli.base import merge as _merge
from saffier.cli.common_params import DirectoryOption, MessageOption
from saffier.cli.state import get_migration_app


@command
def merge(
    message: MessageOption,
    branch_label: Annotated[
        str,
        Option(None, help="Specify a branch label to apply to the new revision"),
    ],
    rev_id: Annotated[
        str,
        Option(None, help="Specify a hardcoded revision id instead of generating one"),
    ],
    revisions: Annotated[list[str], Argument(nargs=-1)],
    directory: DirectoryOption,
) -> None:
    """Merge two revisions together, creating a new revision file"""
    _merge(get_migration_app(), directory, revisions, message, branch_label, rev_id)
