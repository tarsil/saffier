import pytest

import saffier

database = saffier.Database("sqlite+aiosqlite:///m2m_naming.db")
models = saffier.Registry(database=database)


class BasePrefixed(saffier.StrictModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        abstract = True
        registry = models
        table_prefix = "m2m"


class Album(BasePrefixed):
    title = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class User(BasePrefixed):
    albums = saffier.ManyToMany(Album)

    class Meta:
        registry = models


class Label(BasePrefixed):
    title = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Project(BasePrefixed):
    primarytags = saffier.ManyToMany(
        Label,
        through_tablename=saffier.NEW_M2M_NAMING,
    )
    secondarytags = saffier.ManyToMany(
        Label,
        through_tablename=saffier.NEW_M2M_NAMING,
    )

    class Meta:
        registry = models


def test_default_m2m_naming_uses_field_based_through_table() -> None:
    assert User.meta.fields["albums"].through.meta.tablename == "m2m_useralbumsthrough"


def test_explicit_new_m2m_naming_uses_field_based_through_table() -> None:
    assert (
        Project.meta.fields["primarytags"].through.meta.tablename
        == "m2m_projectprimarytagsthrough"
    )


def test_new_m2m_naming_keeps_same_target_relations_distinct() -> None:
    assert (
        Project.meta.fields["primarytags"].through.meta.tablename
        == "m2m_projectprimarytagsthrough"
    )
    assert (
        Project.meta.fields["secondarytags"].through.meta.tablename
        == "m2m_projectsecondarytagsthrough"
    )


def test_string_through_tablename_supports_field_formatting() -> None:
    test_registry = saffier.Registry(
        database=saffier.Database("sqlite+aiosqlite:///m2m_naming_format.db")
    )

    class Team(saffier.StrictModel):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = test_registry

    class Member(saffier.StrictModel):
        teams = saffier.ManyToMany(
            Team,
            through_tablename="custom_{field.owner.__name__}_{field.name}",
        )

        class Meta:
            registry = test_registry

    assert Member.meta.fields["teams"].through.meta.tablename == "custom_member_teams"


def test_non_string_non_marker_through_tablename_is_rejected() -> None:
    test_registry = saffier.Registry(
        database=saffier.Database("sqlite+aiosqlite:///m2m_naming_old.db")
    )

    with pytest.raises(saffier.FieldDefinitionError, match="through_tablename"):

        class Team(saffier.StrictModel):
            name = saffier.CharField(max_length=100)

            class Meta:
                registry = test_registry

        class Member(saffier.StrictModel):
            teams = saffier.ManyToMany(Team, through_tablename=object())

            class Meta:
                registry = test_registry


def test_invalid_through_tablename_is_rejected() -> None:
    test_registry = saffier.Registry(
        database=saffier.Database("sqlite+aiosqlite:///m2m_naming_invalid.db")
    )

    with pytest.raises(saffier.FieldDefinitionError, match="through_tablename"):

        class Team(saffier.StrictModel):
            name = saffier.CharField(max_length=100)

            class Meta:
                registry = test_registry

        class Member(saffier.StrictModel):
            teams = saffier.ManyToMany(Team, through_tablename="")

            class Meta:
                registry = test_registry
