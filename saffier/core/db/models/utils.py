from typing import TYPE_CHECKING, Type, cast

from saffier.core.connection.registry import Registry

if TYPE_CHECKING:
    from saffier.core.db.models import Model


def get_model(registry: Registry, model_name: str) -> Type["Model"]:
    """
    Return the model with capitalize model_name.

    Raise lookup error if no model is found.
    """
    try:
        return cast("Type[Model]", registry.models[model_name])
    except KeyError:
        raise LookupError(f"Registry doesn't have a {model_name} model.") from None
