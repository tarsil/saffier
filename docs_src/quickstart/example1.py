import saffier
from saffier import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


class Note(saffier.Model):
    """
    The Note model to be created in the database as a table
    If no name is provided the in Meta class, it will generate
    a "notes" table for you.
    """

    id = saffier.IntegerField(primary_key=True)
    text = saffier.CharField(max_length=255)
    is_completed = saffier.BooleanField(default=False)

    class Meta:
        registry = models


# Create the db and tables
# Don't use this in production! Use Alembic or any tool to manage
# The migrations for you
await models.create_all()

await Note.query.create(text="Buy the stuff.", is_completed=False)

note = await Note.query.get(id=1)
print(note)
# Note(id=1)
