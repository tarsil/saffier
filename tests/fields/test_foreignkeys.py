import pytest

import saffier
from saffier import ForeignKey, OneToOne, OneToOneField, StrictModel
from saffier.core.db import fields
from saffier.core.db.relationships.related import RelatedField
from saffier.exceptions import FieldDefinitionError


class MyModel(StrictModel):
    name = fields.CharField(max_length=255)

    class Meta:
        abstract = True


@pytest.mark.parametrize("model", [ForeignKey, OneToOne, OneToOneField])
def test_can_create_foreign_key(model):
    fk = model(to=MyModel)

    assert fk is not None
    assert fk.to == MyModel


def test_raise_error_on_delete_fk():
    with pytest.raises(FieldDefinitionError, match="on_delete must not be null."):
        ForeignKey(to=MyModel, on_delete=None)


def test_raise_error_on_delete_null():
    with pytest.raises(FieldDefinitionError, match="When SET_NULL is enabled, null must be True."):
        ForeignKey(to=MyModel, on_delete=saffier.SET_NULL)


def test_raise_error_on_update_null():
    with pytest.raises(FieldDefinitionError, match="When SET_NULL is enabled, null must be True."):
        ForeignKey(to=MyModel, on_update=saffier.SET_NULL)


def test_foreign_key_helper_methods_match_edgy_surface():
    owner_db = type("OwnerDB", (), {"url": "postgresql://owner"})()
    target_db = type("TargetDB", (), {"url": "postgresql://target"})()
    target_registry = type(
        "TargetRegistry", (), {"admin_models": {"Target"}, "database": target_db}
    )()
    owner_registry = type("OwnerRegistry", (), {"admin_models": set(), "database": owner_db})()

    owner = type(
        "Owner",
        (),
        {
            "meta": type("Meta", (), {"registry": owner_registry})(),
            "database": owner_db,
        },
    )
    target = type(
        "Target",
        (),
        {
            "meta": type("Meta", (), {"registry": target_registry})(),
            "database": target_db,
        },
    )

    field = ForeignKey(to=target, on_delete=saffier.CASCADE)
    field.owner = owner

    assert field.is_cross_db()
    assert field.get_related_model_for_admin() is target


def test_related_field_helper_methods_match_edgy_surface():
    owner_db = type("OwnerDB", (), {"url": "postgresql://owner"})()
    target_db = type("TargetDB", (), {"url": "postgresql://target"})()
    source_registry = type(
        "SourceRegistry",
        (),
        {"admin_models": {"Source"}, "database": target_db},
    )()
    owner_registry = type("OwnerRegistry", (), {"admin_models": set(), "database": owner_db})()

    owner = type(
        "Owner",
        (),
        {
            "meta": type("Meta", (), {"registry": owner_registry})(),
            "database": owner_db,
        },
    )
    target = type(
        "Target",
        (),
        {
            "meta": type("Meta", (), {"registry": source_registry})(),
            "database": target_db,
        },
    )
    foreign_key = ForeignKey(to=owner, on_delete=saffier.CASCADE)
    foreign_key.owner = target
    foreign_key.name = "owner"
    foreign_key.related_name = "sources"

    source = type(
        "Source",
        (),
        {
            "__name__": "Source",
            "meta": type(
                "Meta", (), {"fields": {"owner": foreign_key}, "registry": source_registry}
            )(),
            "fields": {"owner": foreign_key},
        },
    )
    foreign_key.owner = source

    related = RelatedField(
        related_name="sources",
        related_to=owner,
        related_from=source,
    )

    assert related.name == "sources"
    assert related.get_foreign_key_field_name() == "owner"
    assert related.is_cross_db()
    assert related.get_related_model_for_admin() is source
