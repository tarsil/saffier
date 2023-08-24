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


# All the users with all the posts and articles
# of each user
users = await User.query.prefetch_related(
    Prefetch(related_name="posts", to_attr="to_posts"),
    Prefetch(related_name="articles", to_attr="to_articles"),
).all()
