import os
import select
import sys
from typing import Any, Dict

import click
from IPython import start_ipython

from saffier import Registry


def import_objects(registry: Registry) -> Dict[Any, Any]:
    """Imports all the needed models"""

    models_to_import = {}
    for _, model in registry.models.items():
        models_to_import[model.__module__] = model
    return models_to_import


def get_ipython_arguments():
    ipython_args = "IPYTHON_ARGUMENTS"
    arguments = os.environ.get(ipython_args, "").split()
    return arguments


@click.command()
@click.pass_context
def shell(ctx: Any) -> None:
    """
    Starts an interactive ipython shell with all the models
    and important python libraries.
    """
    registry = ctx.obj._saffier_db["migrate"].registry

    if (
        sys.platform != "win32"
        and not sys.stdin.isatty()
        and select.select([sys.stdin], [], [], 0)[0]
    ):
        exec(sys.stdin.read(), globals())
        return

    imported_objects = import_objects(registry)
    ipython_arguments = get_ipython_arguments()
    start_ipython(argv=ipython_arguments, user_ns=imported_objects)
    return None
