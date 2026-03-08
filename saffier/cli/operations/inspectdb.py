from typing import Annotated

from sayer import Option, command

from saffier.utils.inspect import InspectDB


@command
def inspect_db(
    database: Annotated[
        str,
        Option(
            required=True,
            help=(
                "Connection string. Example: postgres+asyncpg://user:password@localhost:5432/my_db"
            ),
        ),
    ],
    schema: Annotated[str, Option(None, help="Database schema to be applied.")],
) -> None:
    """Inspect an existing database and print Saffier `ReflectModel` definitions.

    The output is intended as a starting point for reflection-based model modules.
    """
    inspect_db = InspectDB(database=database, schema=schema)
    inspect_db.inspect()
