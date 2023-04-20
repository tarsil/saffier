import datetime
from collections import OrderedDict
from typing import Any, Dict

import pydantic

import saffier
from saffier import Registry
from saffier.core.terminal import OutputColour, Print

printer = Print()

defaults = OrderedDict()

defaults.update(
    {
        "datetime": datetime.datetime,
        "timedelta": datetime.timedelta,
        "BaseModel": pydantic.BaseModel,
        "BaseConfig": pydantic.BaseConfig,
        "settings": saffier.settings,
    }
)


def welcome_message(app: Any):
    """Displays the welcome message for the user"""
    now = datetime.datetime.now().strftime("%b %d %Y, %H:%M:%S")
    saffier_info_date = f"Saffier {saffier.__version__} (interactive shell, {now})"
    info = "Interactive shell that imports the application models and some python defaults."

    application_text = printer.message("Application: ", colour=OutputColour.CYAN3)
    application_name = printer.message(app.__class__.__name__, colour=OutputColour.GREEN3)
    application = f"{application_text}{application_name}"

    printer.write_plain(saffier_info_date, colour=OutputColour.CYAN3)
    printer.write_plain(info, colour=OutputColour.CYAN3)
    printer.write_plain(application)


def import_objects(app: Any, registry: Registry) -> Dict[Any, Any]:
    """
    Imports all the needed objects needed for the shell.
    """
    imported_objects = {}
    import_statement = "from {module_path} import {model}"
    welcome_message(app)
    printer.write_success(79 * "-", colour=OutputColour.CYAN3)

    def import_defaults():
        for name, module in defaults.items():
            directive = import_statement.format(module_path=module.__module__, model=name)
            printer.write_success(directive, colour=OutputColour.CYAN3)
            imported_objects[name] = module

    def import_models():
        # Creates a dict map with module path and model to import
        printer.write_success("Models".center(79, "-"), colour=OutputColour.CYAN3)
        for _, model in sorted(registry.models.items()):
            directive = import_statement.format(module_path=model.__module__, model=model.__name__)
            printer.write_success(directive, colour=OutputColour.CYAN3)
            imported_objects[model.__name__] = model

    def import_reflected_models():
        # Creates a dict map with module path and model to import
        if not registry.reflected:
            return

        printer.write_success("Reflected models".center(79, "-"), colour=OutputColour.CYAN3)
        for _, model in sorted(registry.reflected.items()):
            directive = import_statement.format(module_path=model.__module__, model=model.__name__)
            printer.write_success(directive, colour=OutputColour.CYAN3)
            imported_objects[model.__name__] = model

    import_defaults()
    import_models()
    import_reflected_models()

    return imported_objects
