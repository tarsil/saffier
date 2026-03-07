from saffier.core.db.context_vars import get_schema
from saffier.core.db.querysets.mixins import TenancyMixin, deactivate_schema, with_schema


class _FakeRegistry:
    def __init__(self) -> None:
        self.database = "default-db"
        self.extra = {"analytics": "analytics-db"}


class _FakeModel:
    meta = type("Meta", (), {"registry": _FakeRegistry(), "db_schema": None})
    table = ("table", None)

    @classmethod
    def table_schema(cls, schema):
        return ("table", schema)


class _FakeQuerySet(TenancyMixin):
    def __init__(self) -> None:
        self.model_class = _FakeModel
        self.database = "default-db"
        self.using_schema = None
        self.table = _FakeModel.table

    def _clone(self):
        clone = type(self)()
        clone.database = self.database
        clone.using_schema = self.using_schema
        clone.table = self.table
        return clone


def test_with_schema_restores_previous_value() -> None:
    assert get_schema() is None
    with with_schema("tenant_a"):
        assert get_schema() == "tenant_a"
    assert get_schema() is None


def test_deactivate_schema_resets_context() -> None:
    with with_schema("tenant_a"):
        assert get_schema() == "tenant_a"
        deactivate_schema()
        assert get_schema() is None


def test_using_accepts_keyword_database_and_schema() -> None:
    queryset = _FakeQuerySet()

    switched = queryset.using(database="analytics", schema="tenant_a")
    assert switched.database == "analytics-db"
    assert switched.using_schema == "tenant_a"
    assert switched.table == ("table", "tenant_a")

    reset_schema = queryset.using(schema=False)
    assert reset_schema.using_schema is None
    assert reset_schema.table == ("table", None)
