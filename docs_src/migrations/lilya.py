#!/usr/bin/env python
import os
import sys
from pathlib import Path

from lilya.apps import Lilya
from my_project.utils import get_db_connection

from saffier import Instance, monkay


def build_path():
    """Add the project and application directories to ``sys.path``.

    Migration discovery often runs from a command process rather than the ASGI
    server process. This helper makes the project package and its ``apps``
    directory importable before Saffier loads the registry.
    """
    Path(__file__).resolve().parent.parent
    SITE_ROOT = os.path.dirname(os.path.realpath(__file__))

    if SITE_ROOT not in sys.path:
        sys.path.append(SITE_ROOT)
        sys.path.append(os.path.join(SITE_ROOT, "apps"))


def get_application():
    """Create the Lilya application and bind Saffier's active instance.

    The migration CLI can receive this app through ``--app``. Binding the
    registry to ``saffier.monkay`` gives Saffier one place to discover metadata,
    migrations, and runtime settings for the project.
    """
    build_path()
    database, registry = get_db_connection()

    app = Lilya(__name__)

    monkay.set_instance(Instance(registry=registry, app=app))
    return app


app = get_application()
