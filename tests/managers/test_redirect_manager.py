import saffier

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/saffier")
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


def test_query_related_is_redirect_manager():
    manager = User.query_related

    assert isinstance(manager, saffier.RedirectManager)
    assert manager.model_class is User


def test_query_related_delegates_to_query_manager():
    direct = User.query.filter(name="foo")
    via_related = User.query_related.filter(name="foo")

    assert str(direct._build_select()) == str(via_related._build_select())
