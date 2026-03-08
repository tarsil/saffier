import pytest

import saffier
from saffier.exceptions import ModelReferenceError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)


class TrackRef(saffier.ModelRef):
    __related_name__ = "tracks_set"
    title: str
    position: int


class Album(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    tracks = saffier.RefForeignKey(TrackRef, null=True)

    class Meta:
        registry = models


class Track(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    album = saffier.ForeignKey("Album", on_delete=saffier.CASCADE)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models


class PostRef(saffier.ModelRef):
    __related_name__ = "posts_set"
    comment: str


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100, null=True)
    posts = saffier.RefForeignKey(PostRef, null=True)

    class Meta:
        registry = models


class Post(saffier.StrictModel):
    user = saffier.ForeignKey("User", on_delete=saffier.CASCADE)
    comment = saffier.CharField(max_length=255)

    class Meta:
        registry = models


async def test_model_ref_requires_related_name() -> None:
    with pytest.raises(ModelReferenceError, match="__related_name__"):

        class InvalidPostRef(saffier.ModelRef):
            comment: str


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_ref_foreign_key_creates_related_models_from_dicts() -> None:
    user = await User.query.create(name="foo", posts=[{"comment": "dict"}])

    posts = await user.posts_set.all()

    assert [post.comment for post in posts] == ["dict"]


async def test_ref_foreign_key_accepts_positional_model_refs_on_create() -> None:
    album = await Album.query.create(
        TrackRef(title="The Bird", position=1),
        TrackRef(title="The Waters", position=2),
        name="Malibu",
        tracks=[],
    )

    tracks = await album.tracks_set.order_by("position").all()

    assert [(track.title, track.position) for track in tracks] == [
        ("The Bird", 1),
        ("The Waters", 2),
    ]


async def test_ref_foreign_key_replays_model_refs_on_get_or_create_and_update_or_create() -> None:
    user, created = await User.query.get_or_create(
        PostRef(comment="first"),
        name="foo",
        posts=[],
    )
    assert created is True

    user, created = await User.query.get_or_create(
        PostRef(comment="second"),
        name="foo",
        posts=[],
    )
    assert created is False

    user, created = await User.query.update_or_create(
        PostRef(comment="third"),
        name="foo",
        posts=[],
    )
    assert created is False

    posts = await user.posts_set.order_by("id").all()

    assert [post.comment for post in posts] == ["first", "second", "third"]
