import saffier

database = saffier.Database("sqlite:///db.sqlite")
models = saffier.Registry(database=database)


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    album = saffier.ForeignKey("Album", on_delete=saffier.CASCADE, related_name="tracks")
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models


class Studio(saffier.Model):
    album = saffier.ForeignKey("Album", related_name="studios")
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class Company(saffier.Model):
    studio = saffier.ForeignKey(Studio, related_name="companies")

    class Meta:
        registry = models
