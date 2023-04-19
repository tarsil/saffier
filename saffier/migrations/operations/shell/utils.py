from typing import Any, Dict

from saffier import Registry
from saffier.core.terminal import OutputColour, Print

printer = Print()


def import_objects(registry: Registry) -> Dict[Any, Any]:
    """
    Imports all the needed objects needed for the shell.
    """
    imported_objects = {}
    import_statement = "from {module_path} import {model}"

    # Creates a dict map with module path and model to import
    printer.write_success("Saffier User Pre Imports", colour=OutputColour.GREEN3)
    printer.write_success(80 * "-", colour=OutputColour.GREEN3)
    for _, model in registry.models.items():
        directive = import_statement.format(module_path=model.__module__, model=model.__name__)
        printer.write_success(directive, colour=OutputColour.GREEN3)
        imported_objects[model.__name__] = model

    return imported_objects
