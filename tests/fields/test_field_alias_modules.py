from saffier.core.db.fields.base import (
    AutoNowMixin,
    ComputedField,
    ExcludeField,
    FileField,
    ImageField,
    PGArrayField,
    PlaceholderField,
)
from saffier.core.db.fields.computed_field import ComputedField as ComputedFieldAlias
from saffier.core.db.fields.core import __all__ as core_all
from saffier.core.db.fields.exclude_field import ExcludeField as ExcludeFieldAlias
from saffier.core.db.fields.file_field import FileField as FileFieldAlias
from saffier.core.db.fields.image_field import ImageField as ImageFieldAlias
from saffier.core.db.fields.mixins import AutoNowMixin as AutoNowMixinAlias
from saffier.core.db.fields.place_holder_field import PlaceholderField as PlaceholderFieldAlias
from saffier.core.db.fields.postgres import PGArrayField as PGArrayFieldAlias
from saffier.core.db.fields.types import (
    FieldMapping,
    SupportsColumns,
    SupportsEmbeddedFields,
)


def test_field_alias_modules_export_expected_symbols():
    assert ComputedFieldAlias is ComputedField
    assert ExcludeFieldAlias is ExcludeField
    assert FileFieldAlias is FileField
    assert ImageFieldAlias is ImageField
    assert AutoNowMixinAlias is AutoNowMixin
    assert PlaceholderFieldAlias is PlaceholderField
    assert PGArrayFieldAlias is PGArrayField


def test_field_types_aliases_are_available():
    assert getattr(FieldMapping, "__origin__", dict) is dict
    assert SupportsColumns.__name__ == "SupportsColumns"
    assert SupportsEmbeddedFields.__name__ == "SupportsEmbeddedFields"
    assert "CharField" in core_all
