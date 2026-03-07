import pytest

import saffier
from saffier.core.signals import post_delete, pre_delete
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100)
    profile = saffier.ForeignKey(
        "Profile",
        null=True,
        on_delete=saffier.CASCADE,
        no_constraint=True,
        remove_referenced=True,
        use_model_based_deletion=True,
    )

    class Meta:
        registry = models
        tablename = "deletion_signal_users"


class Profile(saffier.StrictModel):
    name = saffier.CharField(max_length=100)
    __deletion_with_signals__ = True

    class Meta:
        registry = models
        tablename = "deletion_signal_profiles"


class Log(saffier.StrictModel):
    signal = saffier.CharField(max_length=255)
    is_queryset = saffier.BooleanField()
    model_instance_id = saffier.BigIntegerField(null=True)
    row_count = saffier.BigIntegerField(null=True)
    class_name = saffier.CharField(max_length=255)

    class Meta:
        registry = models
        tablename = "deletion_signal_logs"


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


@pytest.fixture(autouse=True, scope="function")
async def connect_signals():
    @pre_delete([Profile, User])
    async def pre_deleting(sender, instance, model_instance=None, **kwargs):
        await Log.query.create(
            signal="pre_delete",
            is_queryset=model_instance is None,
            model_instance_id=getattr(model_instance, "id", None),
            class_name=instance.model_class.__name__
            if model_instance is None
            else type(model_instance).__name__,
        )

    @post_delete([Profile, User])
    async def post_deleting(sender, instance, model_instance=None, row_count=None, **kwargs):
        await Log.query.create(
            signal="post_delete",
            is_queryset=model_instance is None,
            model_instance_id=getattr(model_instance, "id", None),
            row_count=row_count,
            class_name=instance.model_class.__name__
            if model_instance is None
            else type(model_instance).__name__,
        )

    try:
        yield
    finally:
        Profile.meta.signals.pre_delete.disconnect(pre_deleting)
        Profile.meta.signals.post_delete.disconnect(post_deleting)
        User.meta.signals.pre_delete.disconnect(pre_deleting)
        User.meta.signals.post_delete.disconnect(post_deleting)


@pytest.mark.parametrize("klass", [User, Profile])
async def test_deletion_called_once_model(klass):
    obj = await klass.query.create(name="Edgy")

    await obj.delete()

    logs = await Log.query.order_by("id").all()
    assert len(logs) == 2
    assert logs[0].signal == "pre_delete"
    assert logs[0].class_name == klass.__name__
    assert logs[0].is_queryset is False
    assert logs[1].signal == "post_delete"
    assert logs[1].class_name == klass.__name__
    assert logs[1].is_queryset is False


async def test_deletion_called_once_query():
    await User.query.create(name="Edgy")

    await User.query.delete()

    logs = await Log.query.order_by("id").all()
    assert len(logs) == 2
    assert logs[0].signal == "pre_delete"
    assert logs[0].class_name == "User"
    assert logs[0].is_queryset is True
    assert logs[1].signal == "post_delete"
    assert logs[1].class_name == "User"
    assert logs[1].is_queryset is True


async def test_deletion_called_referenced():
    profile = await Profile.query.create(name="Profile")
    user = await User.query.create(name="Edgy", profile=profile)

    await user.delete()

    logs = await Log.query.order_by("id").all()
    assert [(log.signal, log.class_name) for log in logs] == [
        ("pre_delete", "User"),
        ("pre_delete", "Profile"),
        ("post_delete", "Profile"),
        ("post_delete", "User"),
    ]


async def test_deletion_called_cascade():
    profile = await Profile.query.create(name="Profile")
    await User.query.create(name="Edgy", profile=profile)
    await User.query.create(name="Edgy2", profile=profile)

    await profile.delete()

    logs = await Log.query.order_by("id").all()
    assert len(logs) == 2
    assert logs[0].signal == "pre_delete"
    assert logs[0].class_name == "Profile"
    assert logs[1].signal == "post_delete"
    assert logs[1].class_name == "Profile"


async def test_deletion_called_cascade_with_signals():
    profile = await Profile.query.create(name="Profile")
    await User.query.create(name="Edgy", profile=profile)
    await User.query.create(name="Edgy2", profile=profile)

    User.__deletion_with_signals__ = True
    try:
        await profile.delete()
    finally:
        User.__deletion_with_signals__ = False

    logs = await Log.query.order_by("id").all()
    assert len(logs) == 6
    assert (logs[0].signal, logs[0].class_name) == ("pre_delete", "Profile")
    assert (logs[-1].signal, logs[-1].class_name) == ("post_delete", "Profile")
    assert sum(1 for log in logs if (log.signal, log.class_name) == ("pre_delete", "User")) == 2
    assert sum(1 for log in logs if (log.signal, log.class_name) == ("post_delete", "User")) == 2
