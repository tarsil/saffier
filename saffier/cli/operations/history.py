from typing import Annotated

from sayer import Option, command

from saffier.cli.base import history as _history
from saffier.cli.common_params import DirectoryOption, VerboseOption
from saffier.cli.state import get_migration_app


@command
def history(
    rev_range: Annotated[
        str | None,
        Option(
            None, "-r", "--rev-range", help="Specify a revision range; format is [start]:[end]"
        ),
    ],
    verbose: VerboseOption,
    indicate_current: Annotated[
        bool,
        Option(
            False,
            "-i",
            is_flag=True,
            help=("Indicate current version (Alembic 0.9.9 or greater is required)"),
        ),
    ],
    directory: DirectoryOption,
) -> None:
    """List changeset scripts in chronological order."""
    _history(get_migration_app(), directory, rev_range, verbose, indicate_current)
