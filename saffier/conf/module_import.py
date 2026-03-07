from importlib import import_module
from typing import Any


def import_string(dotted_path: str) -> Any:
    """
    Import a dotted or ``module:attribute`` path and return the designated object.
    """
    if ":" in dotted_path:
        module_path, class_name = dotted_path.split(":", 1)
    else:
        try:
            module_path, class_name = dotted_path.rsplit(".", 1)
        except ValueError as err:
            raise ImportError(f"{dotted_path} doesn't look like a module path") from err

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError(
            f'Module "{module_path}" does not define a "{class_name}" attribute/class'
        ) from err
