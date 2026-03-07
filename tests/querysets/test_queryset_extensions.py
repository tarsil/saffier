import pytest
import sqlalchemy

import saffier
from saffier.exceptions import QuerySetError

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/saffier")
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class Group(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


def test_reverse_adds_desc_when_no_ordering():
    queryset = User.query.reverse()

    assert queryset._order_by == ("-id",)


def test_reverse_flips_existing_ordering():
    queryset = User.query.order_by("name", "-id").reverse()

    assert queryset._order_by == ("-name", "id")


def test_batch_size_sets_chunk_size():
    queryset = User.query.batch_size(25)

    assert queryset._batch_size == 25


def test_local_or_adds_or_clause():
    queryset = User.query.filter(name="Alice").local_or(name="Bob")

    assert len(queryset.filter_clauses) == 1
    assert len(queryset.or_clauses) == 1


def test_extra_select_appends_expression():
    queryset = User.query.extra_select(sqlalchemy.literal(1).label("marker"))
    expression = queryset._build_select()

    assert "marker" in str(expression)


def test_reference_select_tracks_named_expression():
    queryset = User.query.reference_select({"marker": sqlalchemy.literal(1)})
    expression = queryset._build_select()

    assert "marker" in queryset._reference_select
    assert "marker" not in str(expression)


@pytest.mark.anyio
async def test_as_select_returns_select_expression():
    expression = await User.query.filter(name="Alice").as_select()

    assert isinstance(expression, sqlalchemy.sql.Select)


def test_select_for_update_builds_locking_clause():
    queryset = User.query.select_for_update(nowait=True, skip_locked=True, read=True)
    expression = queryset._build_select()

    sql = str(expression)
    assert "FOR UPDATE" in sql


def test_transaction_proxy_is_available():
    transaction = User.query.transaction(force_rollback=True)

    assert hasattr(transaction, "__aenter__")
    assert hasattr(transaction, "__aexit__")


@pytest.mark.parametrize(
    ("operation", "token"),
    [
        ("union", "UNION"),
        ("union_all", "UNION ALL"),
        ("intersect", "INTERSECT"),
        ("intersect_all", "INTERSECT ALL"),
        ("except_", "EXCEPT"),
        ("except_all", "EXCEPT ALL"),
    ],
)
def test_set_operations_build_expected_sql(operation, token):
    base = User.query.filter(name__icontains="a")
    other = User.query.filter(name__icontains="b")
    queryset = getattr(base, operation)(other)

    sql = str(queryset._build_select())
    assert token in sql


def test_set_operations_reject_different_models():
    with pytest.raises(QuerySetError):
        User.query.union(Group.query.filter())
