import pytest

import saffier
from saffier import ForeignKey, OneToOne, OneToOneField, StrictModel
from saffier.core.db import fields
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
