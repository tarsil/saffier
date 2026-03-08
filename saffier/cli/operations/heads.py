from typing import Annotated

from sayer import Option, command

from saffier.cli.base import heads as _heads
from saffier.cli.common_params import DirectoryOption, VerboseOption
from saffier.cli.state import get_migration_app


@command
def heads(
    verbose: VerboseOption,
    resolve_dependencies: Annotated[
        bool,
        Option(False, is_flag=True, help="Treat dependency versions as down revisions"),
    ],
    directory: DirectoryOption,
) -> None:
    """Show all head revisions in the migration repository."""
    _heads(get_migration_app(), directory, verbose, resolve_dependencies)
