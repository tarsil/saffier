import asyncio
import contextlib
import select
import sys
from collections.abc import Callable, Iterator, Sequence
from typing import Annotated, Any

from sayer import Option, command, error

from saffier import Registry
from saffier.cli.operations.shell.enums import ShellOption
from saffier.cli.state import get_migration_app, get_migration_registry
from saffier.core.events import AyncLifespanContextManager
from saffier.core.sync import execsync
from saffier.core.utils.sync import _temporary_loop_reentry


@command
def shell(
    kernel: Annotated[
        str,
        Option(
            "ipython",
            help="Which shell should start.",
            show_default=True,
        ),
    ],
) -> None:
    """
    Starts an interactive ipython shell with all the models
    and important python libraries.

    This can be used with a Migration class or with SaffierExtra object lookup.
    """
    if kernel not in {ShellOption.IPYTHON, ShellOption.PTPYTHON}:
        allowed = ", ".join([ShellOption.IPYTHON, ShellOption.PTPYTHON])
        error(f"Invalid shell '{kernel}'. Allowed values: {allowed}.")
        sys.exit(1)

    app = get_migration_app()
    registry = get_migration_registry()

    if (
        sys.platform != "win32"
        and not sys.stdin.isatty()
        and select.select([sys.stdin], [], [], 0)[0]
    ):
        exec(sys.stdin.read(), globals())
        return

    on_startup = getattr(app, "on_startup", [])
    on_shutdown = getattr(app, "on_shutdown", [])
    lifespan = getattr(app, "lifespan", None)
    lifespan = handle_lifespan_events(
        on_startup=on_startup, on_shutdown=on_shutdown, lifespan=lifespan
    )
    execsync(run_shell)(app, lifespan, registry, kernel)
    return None


async def run_shell(app: Any, lifespan: Any, registry: Registry, kernel: str) -> None:
    """Run the interactive shell within the app and registry context.

    Lifespan startup and shutdown hooks are honored when available so the shell
    sees the same initialized state as the running application.
    """
    if lifespan is None:
        if kernel == ShellOption.IPYTHON:
            from saffier.cli.operations.shell.ipython import get_ipython

            _run_shell_with_loop_reentry(get_ipython(app=app, registry=registry))
        else:
            from saffier.cli.operations.shell.ptpython import get_ptpython

            _run_shell_with_loop_reentry(get_ptpython(app=app, registry=registry))
        return

    async with lifespan(app):
        if kernel == ShellOption.IPYTHON:
            from saffier.cli.operations.shell.ipython import get_ipython

            ipython_shell = get_ipython(app=app, registry=registry)
            _run_shell_with_loop_reentry(ipython_shell)
        else:
            from saffier.cli.operations.shell.ptpython import get_ptpython

            ptpython = get_ptpython(app=app, registry=registry)
            _run_shell_with_loop_reentry(ptpython)


@contextlib.contextmanager
def _shell_loop_reentry() -> Iterator[None]:
    """Temporarily permit nested event-loop use while a shell is active.

    Embedded IPython and ptpython sessions are synchronous callables launched
    from Saffier's async lifespan runner. While the shell owns the thread, users
    may still execute async ORM commands that need the already-initialized
    SQLAlchemy event loop. This context uses the same scoped re-entry helper as
    ``saffier.run_sync()`` so shell support does not leave global asyncio state
    patched after the interactive session exits.

    Yields:
        None: Control while the active event loop can be re-entered.
    """
    with _temporary_loop_reentry(asyncio.get_running_loop()):
        yield


def _run_shell_with_loop_reentry(shell_runner: Callable[[], None]) -> None:
    """Execute one interactive shell callable inside a scoped loop patch.

    Args:
        shell_runner: Callable returned by the selected shell backend. It owns
            the terminal session until the user exits IPython or ptpython.
    """
    with _shell_loop_reentry():
        shell_runner()


def handle_lifespan_events(
    on_startup: Sequence[Callable] | None = None,
    on_shutdown: Sequence[Callable] | None = None,
    lifespan: Any | None = None,
) -> Any:
    """Handles with the lifespan events in the new Starlette format of lifespan.
    This adds a mask that keeps the old `on_startup` and `on_shutdown` events variable
    declaration for legacy and comprehension purposes and build the async context manager
    for the lifespan.
    """
    if lifespan:
        return lifespan
    return AyncLifespanContextManager(on_startup=on_startup, on_shutdown=on_shutdown)
