import copy

import saffier
from saffier import Instance, get_migration_prepared_registry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class Tag(saffier.Model):
    label = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Profile(saffier.Model):
    name = saffier.CharField(max_length=100)
    tags = saffier.ManyToMany(
        Tag,
        through_tablename=saffier.NEW_M2M_NAMING,
    )

    class Meta:
        registry = models


def test_instance_bootstrap_prepares_registry_copy_with_generated_m2m_models():
    instance = Instance(registry=models)
    saffier.monkay.set_instance(instance)
    try:
        copied_registry = get_migration_prepared_registry(copy.copy(models))
        copied_profile = copied_registry.get_model("Profile")
        through = copied_profile.meta.fields["tags"].through

        assert copied_profile.meta.fields["tags"].target is copied_registry.get_model("Tag")
        assert through is copied_registry.get_model(through.__name__)
        assert through.meta.tablename == "profiletagsthrough"
    finally:
        saffier.monkay.set_instance(None)
