from typing import Annotated

from sayer import Option, command

from saffier.cli.base import revision as _revision
from saffier.cli.common_params import DirectoryOption, MessageOption, SQLOption
from saffier.cli.state import get_migration_app


@command(context_settings={"ignore_unknown_options": True})
def revision(
    message: MessageOption,
    autogenerate: Annotated[
        bool,
        Option(
            False,
            is_flag=True,
            help=(
                "Populate revision script with candidate migration operations, based on "
                "comparison of database to model"
            ),
        ),
    ],
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
        str | None,
        Option(None, help="Specify a branch label to apply to the new revision"),
    ],
    version_path: Annotated[
        str | None,
        Option(None, help="Specify specific path from config for version file"),
    ],
    rev_id: Annotated[
        str | None,
        Option(None, help="Specify a hardcoded revision id instead of generating one"),
    ],
    directory: DirectoryOption,
) -> None:
    """Create a new revision file."""
    _revision(
        get_migration_app(),
        directory,
        message,
        autogenerate,
        sql,
        head,
        splice,
        branch_label,
        version_path,
        rev_id,
    )
