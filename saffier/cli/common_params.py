from typing import Annotated, Any

from sayer import Argument, Option


def directory_callback(ctx: Any, param: str, value: str | None) -> str | None:
    if value is not None:
        from saffier.conf import settings

        settings.migration_directory = value
    return value


VerboseOption = Annotated[
    bool,
    Option(
        False,
        "-v",
        is_flag=True,
        help="Use more verbose output",
    ),
]
SQLOption = Annotated[
    bool,
    Option(
        False,
        is_flag=True,
        help=("Don't emit SQL to database - dump to standard output instead"),
    ),
]
RevisionHeadArgument = Annotated[str, Argument("head")]
TagOption = Annotated[
    str | None,
    Option(
        None,
        help='Arbitrary "tag" name - can be used by custom env.py scripts',
    ),
]
ExtraArgOption = Annotated[
    list[str],
    Option((), "-x", multiple=True, help="Additional arguments consumed by custom env.py scripts"),
]
MessageOption = Annotated[str | None, Option(None, "-m", help="Revision message")]
DirectoryOption = Annotated[
    str | None,
    Option(
        None,
        "-d",
        help='Migration script directory (default is "migrations")',
        callback=directory_callback,
    ),
]
