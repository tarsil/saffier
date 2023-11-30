import saffier
from saffier import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(saffier.Model):
    first_name: str = saffier.CharField(max_length=50, null=True)
    email: str = saffier.EmailField(max_lengh=100, null=True)

    class Meta:
        registry = models
