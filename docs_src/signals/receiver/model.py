import saffier

database = saffier.Database("sqlite:///db.sqlite")
registry = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.BigIntegerField(primary_key=True)
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=255)
    is_verified = saffier.BooleanField(default=False)

    class Meta:
        registry = registry
