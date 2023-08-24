import pytest

import saffier
from saffier.core.db.querysets import Prefetch
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
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


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_multiple_prefetch_model_calls():
    user = await User.query.create(name="Saffier")

    for i in range(5):
        await Post.query.create(comment="Comment number %s" % i, user=user)

    for i in range(50):
        await Article.query.create(content="Comment number %s" % i, user=user)

    esmerald = await User.query.create(name="Esmerald")

    for i in range(15):
        await Post.query.create(comment="Comment number %s" % i, user=esmerald)

    for i in range(20):
        await Article.query.create(content="Comment number %s" % i, user=esmerald)

    users = await User.query.prefetch_related(
        Prefetch(related_name="posts", to_attr="to_posts"),
        Prefetch(related_name="articles", to_attr="to_articles"),
    ).all()

    assert len(users) == 2

    user1 = [value for value in users if value.pk == user.pk][0]
    assert len(user1.to_posts) == 5
    assert len(user1.to_articles) == 50

    user2 = [value for value in users if value.pk == esmerald.pk][0]
    assert len(user2.to_posts) == 15
    assert len(user2.to_articles) == 20
