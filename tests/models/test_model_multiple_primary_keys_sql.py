import saffier
from saffier import Registry
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

database = DatabaseTestClient(DATABASE_URL, full_isolation=False)
models = Registry(database=database)


class User(saffier.StrictModel):
    non_default_id = saffier.BigIntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, primary_key=True)
    language = saffier.CharField(max_length=200, null=True)
    parent = saffier.ForeignKey(
        "User", on_delete=saffier.SET_NULL, null=True, related_name="children"
    )

    class Meta:
        registry = models
        tablename = "composite_users"


def test_composite_primary_key_table_and_lookup_sql():
    pk_value = {"non_default_id": 1, "name": "edgy"}

    assert User.pknames == ("non_default_id", "name")
    assert User.pkcolumns == ("non_default_id", "name")
    assert list(User.table.columns.keys()) == [
        "non_default_id",
        "name",
        "language",
        "parent_non_default_id",
        "parent_name",
    ]

    filter_sql = User.query.filter(pk=pk_value).sql
    assert "composite_users.non_default_id" in filter_sql
    assert "composite_users.name" in filter_sql

    in_sql = User.query.filter(pk__in=[pk_value, {"non_default_id": 2, "name": "other"}]).sql
    assert " OR " in in_sql
    assert in_sql.count("composite_users.non_default_id") >= 2
    assert in_sql.count("composite_users.name") >= 2

    fk_sql = User.query.filter(parent=pk_value).sql
    assert "composite_users.parent_non_default_id" in fk_sql
    assert "composite_users.parent_name" in fk_sql

    join_sql = User.query.select_related("parent").filter(parent__pk=pk_value).sql
    assert "composite_users.parent_non_default_id" in join_sql
    assert 'JOIN composite_users AS "' in join_sql
    assert ".non_default_id" in join_sql
    assert ".name" in join_sql


def test_composite_foreign_key_column_payload_round_trip():
    payload = {
        "non_default_id": 2,
        "name": "edgy2",
        "language": "EN",
        "parent_non_default_id": 1,
        "parent_name": "edgy",
    }

    user = User(**payload)

    assert user.pk == {"non_default_id": 2, "name": "edgy2"}
    assert user.parent.pk == {"non_default_id": 1, "name": "edgy"}
    assert User.extract_column_values(user.extract_db_fields()) == payload
