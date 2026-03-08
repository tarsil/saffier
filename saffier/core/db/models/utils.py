from typing import TYPE_CHECKING, cast

from saffier.core.connection.registry import Registry

if TYPE_CHECKING:
    from saffier.core.db.models import Model


def get_model(registry: Registry, model_name: str) -> type["Model"]:
    """
    Return the model with capitalize model_name.

    Raise lookup error if no model is found.
    """
    return cast("type[Model]", registry.get_model(model_name))
