import saffier
from saffier import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)
    email = saffier.EmailField(max_length=70)
    is_active = saffier.BooleanField(default=True)

    class Meta:
        registry = models
        unique_together = ["name", "email"]


# Using ipython that supports await
# Don't use this in production! Use Alembic or any tool to manage
# The migrations for you
await models.create_all()

await User.query.create(name="Saffier", email="foo@bar.com")

user = await User.query.get(id=1)
# User(id=1)
