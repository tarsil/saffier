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
    schema: Annotated[str | None, Option(None, help="Database schema to be applied.")],
) -> None:
    """
    Inspects an existing database and generates the Saffier reflect models.
    """
    inspect_db = InspectDB(database=database, schema=schema)
    inspect_db.inspect()
