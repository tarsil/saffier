import saffier

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/saffier")
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


def test_reverse_adds_desc_when_no_ordering():
    queryset = User.query.reverse()

    assert queryset._order_by == ("-id",)


def test_reverse_flips_existing_ordering():
    queryset = User.query.order_by("name", "-id").reverse()

    assert queryset._order_by == ("-name", "id")


def test_select_for_update_builds_locking_clause():
    queryset = User.query.select_for_update(nowait=True, skip_locked=True, read=True)
    expression = queryset._build_select()

    sql = str(expression)
    assert "FOR UPDATE" in sql


def test_transaction_proxy_is_available():
    transaction = User.query.transaction(force_rollback=True)

    assert hasattr(transaction, "__aenter__")
    assert hasattr(transaction, "__aexit__")
