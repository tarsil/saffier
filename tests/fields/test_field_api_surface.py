import saffier


def test_field_module_exports_match_public_api() -> None:
    from saffier.core.db.fields.composite_field import CompositeField
    from saffier.core.db.fields.foreign_keys import ForeignKey, RefForeignKey
    from saffier.core.db.fields.many_to_many import ManyToMany, ManyToManyField
    from saffier.core.db.fields.one_to_one_keys import OneToOne, OneToOneField
    from saffier.core.db.fields.ref_foreign_key import RefForeignKey as RefForeignKeyAlias

    assert CompositeField is saffier.CompositeField
    assert ForeignKey is saffier.ForeignKey
    assert RefForeignKey is saffier.RefForeignKey
    assert RefForeignKeyAlias is saffier.RefForeignKey
    assert ManyToMany is saffier.ManyToMany
    assert ManyToManyField is saffier.ManyToManyField
    assert OneToOne is saffier.OneToOne
    assert OneToOneField is saffier.OneToOneField


def test_make_field_factory_applies_defaults_and_overrides() -> None:
    from saffier.core.db.fields.factories import make_field

    SlugField = make_field(saffier.CharField, max_length=80, index=True)
    field = SlugField(unique=True)

    assert isinstance(field, saffier.CharField)
    assert field.index is True
    assert field.unique is True
    assert field.validator.max_length == 80
