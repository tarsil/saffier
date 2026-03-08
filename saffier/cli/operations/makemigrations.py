"""
Client to interact with Saffier models and migrations.
"""

from typing import Annotated

from sayer import Option, command

from saffier.cli.base import migrate as _migrate
from saffier.cli.common_params import DirectoryOption, ExtraArgOption, MessageOption, SQLOption
from saffier.cli.state import get_migration_app


@command(context_settings={"ignore_unknown_options": True})
def makemigrations(
    message: MessageOption,
    sql: SQLOption,
    head: Annotated[
        str,
        Option(
            default="head",
            help="Specify head revision or <branchname>@head to base new revision on",
        ),
    ],
    splice: Annotated[
        bool,
        Option(
            False,
            is_flag=True,
            help='Allow a non-head revision as the "head" to splice onto',
        ),
    ],
    branch_label: Annotated[
        str,
        Option(None, help="Specify a branch label to apply to the new revision"),
    ],
    version_path: Annotated[
        str,
        Option(None, help="Specify specific path from config for version file"),
    ],
    rev_id: Annotated[
        str,
        Option(None, help="Specify a hardcoded revision id instead of generating one"),
    ],
    arg: ExtraArgOption,
    directory: DirectoryOption,
) -> None:
    """Autogenerate a new revision file (alias for `revision --autogenerate`)."""
    _migrate(
        get_migration_app(),
        directory,
        message,
        sql,
        head,
        splice,
        branch_label,
        version_path,
        rev_id,
        arg,
    )
