import saffier
from saffier import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=50)
    email = saffier.EmailField(max_lengh=100)
    password = saffier.CharField(max_length=1000, secret=True)

    class Meta:
        registry = models
