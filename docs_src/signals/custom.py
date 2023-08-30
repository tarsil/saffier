import saffier

database = saffier.Database("sqlite:///db.sqlite")
registry = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.BigIntegerField(primary_key=True)
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=255)

    class Meta:
        registry = registry


# Create the custom signal
User.meta.signals.on_verify = saffier.Signal()
