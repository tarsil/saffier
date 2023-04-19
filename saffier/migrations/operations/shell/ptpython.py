import os
import sys
import typing

from saffier import Registry
from saffier.core.terminal import Print
from saffier.migrations.operations.shell.utils import import_objects

printer = Print()


def use_vi_mode():
    editor = os.environ.get("EDITOR")
    if not editor:
        return False
    editor = os.path.basename(editor)
    return editor.startswith("vi") or editor.endswith("vim")


def get_ptpython(registry: Registry, options: typing.Any = None) -> typing.Any:
    """Gets the IPython shell"""
    try:
        from ptpython.repl import embed, run_config

        def run_ptpython():
            imported_objects = import_objects(registry)
            history_filename = os.path.expanduser("~/.ptpython_history")
            embed(
                globals=imported_objects,
                history_filename=history_filename,
                vi_mode=use_vi_mode(),
                configure=run_config,
            )

    except (ModuleNotFoundError, ImportError):
        error = "You must have IPython installed to run this. Run `pip install saffier[ipython]`"
        printer.write_error(error)
        sys.exit(1)

    return run_ptpython
