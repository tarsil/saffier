import saffier
from saffier import Database, Index, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)
    email = saffier.EmailField(max_length=70)
    is_active = saffier.BooleanField(default=True)
    status = saffier.CharField(max_length=255)

    class Meta:
        registry = models
        unique_together = [
            Index(fields=["name", "email"]),
            Index(fields=["is_active", "statux"], name="active_status_idx"),
        ]
