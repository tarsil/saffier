import os
import sys
import typing

from saffier import Registry
from saffier.conf import settings
from saffier.core.terminal import Print
from saffier.migrations.operations.shell.utils import import_objects

printer = Print()


def vi_mode():
    editor = os.environ.get("EDITOR")
    if not editor:
        return False
    editor = os.path.basename(editor)
    return editor.startswith("vi") or editor.endswith("vim")


def get_ptpython(app: typing.Any, registry: Registry, options: typing.Any = None) -> typing.Any:
    """Gets the PTPython shell.

    Loads the initial configurations from the main Saffier settings
    and boots up the kernel.
    """
    try:
        from ptpython.repl import embed, run_config

        def run_ptpython():
            imported_objects = import_objects(app, registry)
            history_filename = os.path.expanduser("~/.ptpython_history")

            config_file = os.path.expanduser(settings.ptpython_config_file)
            if not os.path.exists(config_file):
                embed(
                    globals=imported_objects,
                    history_filename=history_filename,
                    vi_mode=vi_mode(),
                )
            else:
                embed(
                    globals=imported_objects,
                    history_filename=history_filename,
                    vi_mode=vi_mode(),
                    configure=run_config,
                )

    except (ModuleNotFoundError, ImportError):
        error = "You must have IPython installed to run this. Run `pip install saffier[ipython]`"
        printer.write_error(error)
        sys.exit(1)

    return run_ptpython
