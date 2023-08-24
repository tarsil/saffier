import saffier
from saffier import Prefetch

database = saffier.Database("sqlite:///db.sqlite")
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Post(saffier.Model):
    user = saffier.ForeignKey(User, related_name="posts")
    comment = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class Article(saffier.Model):
    user = saffier.ForeignKey(User, related_name="articles")
    content = saffier.CharField(max_length=255)

    class Meta:
        registry = models


# All the tracks that belong to a specific `Company`.
# The tracks are associated with `albums` and `studios`
company = await Company.query.prefetch_related(
    Prefetch(related_name="companies__studios__tracks", to_attr="tracks")
).get(studio=studio)
