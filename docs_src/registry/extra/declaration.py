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
