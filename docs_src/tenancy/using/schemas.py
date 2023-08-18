import saffier
from saffier import Database, Registry

database = Database("<YOUR-CONNECTION-STRING>")
models = Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    is_active = saffier.BooleanField(default=False)

    class Meta:
        registry = models
