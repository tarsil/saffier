import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database

database = Database("<YOUR-CONNECTION-STRING>")
alternative = Database("<YOUR-ALTERNATIVE-CONNECTION-STRING>")
models = saffier.Registry(database=database, extra={"alternative": alternative})


class User(saffier.Model):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255)

    class Meta:
        registry = models


async def bulk_create_users() -> None:
    """
    Bulk creates some users.
    """
    await User.query.using_with_db("alternative").bulk_create(
        [
            {"name": "Edgy", "email": "saffier@example.com"},
            {"name": "Edgy Alternative", "email": "saffier.alternative@example.com"},
        ]
    )
