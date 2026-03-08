from typing import Annotated

from sayer import Option, command

from saffier.cli.base import init as _init
from saffier.cli.common_params import DirectoryOption


@command
def init(
    template: Annotated[
        str,
        Option(None, "-t", help='Repository template to use (default is "default")'),
    ],
    package: Annotated[
        bool,
        Option(
            False,
            is_flag=True,
            help="Write empty __init__.py files to the environment and version locations",
        ),
    ],
    directory: DirectoryOption,
) -> None:
    """Create a new migration repository.

    This is the user-facing entry point for repository initialization.
    """
    _init(None, directory, template, package)
