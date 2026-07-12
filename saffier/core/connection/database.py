"""Native SQLAlchemy Async database runtime for Saffier.

This module is the runtime boundary between Saffier's ORM layer and
SQLAlchemy 2.x. It owns URL handling, async engine/session creation,
connection-scoped execution helpers, transaction scopes, and the test database
client without delegating database work outside SQLAlchemy.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import weakref
from collections.abc import AsyncGenerator, Callable, Iterator, Sequence
from contextvars import ContextVar, Token
from functools import cached_property, wraps
from typing import Any, TypeVar, cast
from urllib.parse import SplitResult, parse_qs, quote, unquote, urlencode, urlsplit

import orjson
import sqlalchemy
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    AsyncTransaction,
    async_sessionmaker,
    create_async_engine,
)

try:
    from monkay.asgi import ASGIApp, LifespanHook
except Exception:  # pragma: no cover - optional integration import guard
    ASGIApp = Any  # type: ignore[misc,assignment]
    LifespanHook = None  # type: ignore[assignment]


_CallableType = TypeVar("_CallableType", bound=Callable[..., Any])


def _coerce_statement(query: sqlalchemy.ClauseElement | str) -> sqlalchemy.ClauseElement:
    """Normalize public execution input into a SQLAlchemy statement.

    Saffier's low-level helpers accept both SQLAlchemy clause elements and raw
    SQL strings. SQLAlchemy's async execution path expects a clause element, so
    strings are wrapped with ``sqlalchemy.text()`` while already-built
    statements pass through unchanged.
    """
    return sqlalchemy.text(query) if isinstance(query, str) else query


def _async_url(url: DatabaseURL) -> URL:
    """Build the SQLAlchemy URL used to create the async engine.

    Public Saffier URLs may omit the async driver for common dialects because
    older examples used plain ``postgresql://`` or ``sqlite://`` schemes. This
    helper keeps those URLs accepted while selecting SQLAlchemy's async drivers
    before ``create_async_engine()`` is called.
    """
    sqla_url = url.sqla_url
    if sqla_url.drivername in {"sqlite", "postgres", "postgresql", "mysql"}:
        drivers = {
            "sqlite": "sqlite+aiosqlite",
            "postgres": "postgresql+asyncpg",
            "postgresql": "postgresql+asyncpg",
            "mysql": "mysql+asyncmy",
        }
        return sqla_url.set(drivername=drivers[sqla_url.drivername])
    return sqla_url


def _json_serializer(value: Any) -> str:
    """Serialize Python JSON values for SQLAlchemy engine options.

    SQLAlchemy dialects such as asyncpg can receive serializer hooks at engine
    creation time. Saffier uses ``orjson`` here so JSON field behavior stays
    consistent with the rest of the ORM while the engine remains native
    SQLAlchemy.
    """
    return orjson.dumps(value).decode("utf8")


def _json_deserializer(value: str | bytes | bytearray) -> Any:
    """Deserialize JSON payloads returned through SQLAlchemy dialect hooks.

    Driver implementations may hand back text or bytes. Routing through
    ``orjson.loads`` keeps Saffier's JSON handling centralized without adding a
    database runtime layer above SQLAlchemy.
    """
    return orjson.loads(value)


def _batch_rows(rows: Sequence[Any], batch_size: int) -> Iterator[Sequence[Any]]:
    """Split an in-memory result sequence into stable batch slices.

    ``Database.batched_iterate()`` keeps a compatibility API that yields grouped
    rows. This helper performs that grouping with basic slicing so Saffier does
    not need newer ``itertools`` helpers unavailable on older supported Python
    versions.
    """
    for index in range(0, len(rows), batch_size):
        yield rows[index : index + batch_size]


ACTIVE_FORCE_ROLLBACKS: ContextVar[weakref.WeakKeyDictionary[Any, bool] | None] = ContextVar(
    "ACTIVE_FORCE_ROLLBACKS",
    default=None,
)


class ForceRollback:
    """Context-local boolean flag controlling forced rollback behavior.

    The flag has a default value, but tests and schema helpers can temporarily
    override it in the current context with ``database.force_rollback(True)`` or
    ``database.force_rollback(False)``.
    """

    default: bool

    def __init__(self, default: bool) -> None:
        """Create a rollback flag with its process-level default.

        The flag is later read through context-local overrides, so the default
        represents the behavior for code that has not explicitly entered a
        ``database.force_rollback(...)`` block.
        """
        self.default = default

    def set(self, value: bool | None = None) -> None:
        """Set or clear this flag in the current context.

        A copied weak-key dictionary is written back into the context variable
        so nested tests can isolate their override without mutating rollback
        state that belongs to a parent task or another database instance.
        """
        force_rollbacks = ACTIVE_FORCE_ROLLBACKS.get()
        if force_rollbacks is None:
            if value is None:
                return
            force_rollbacks = weakref.WeakKeyDictionary()
        else:
            force_rollbacks = force_rollbacks.copy()
        if value is None:
            force_rollbacks.pop(self, None)
        else:
            force_rollbacks[self] = value
        ACTIVE_FORCE_ROLLBACKS.set(force_rollbacks)

    def __bool__(self) -> bool:
        """Resolve the rollback state visible to the current task.

        Context-specific values win over the constructor default. This lets
        tests temporarily enable or disable forced rollback while unrelated
        execution paths keep the configured default.
        """
        force_rollbacks = ACTIVE_FORCE_ROLLBACKS.get()
        if force_rollbacks is None:
            return self.default
        return force_rollbacks.get(self, self.default)

    @contextlib.contextmanager
    def __call__(self, force_rollback: bool = True) -> Iterator[None]:
        """Temporarily override rollback mode inside a synchronous block.

        The previous effective value is restored on exit, including when the
        block raises. This mirrors the public behavior Saffier exposes for
        scoped test isolation flags.
        """
        initial = bool(self)
        self.set(force_rollback)
        try:
            yield
        finally:
            self.set(initial)


class ForceRollbackDescriptor:
    """Expose ``database.force_rollback`` as both a value and scoped mutator.

    The descriptor keeps the public attribute ergonomic while the actual state
    lives in ``ForceRollback``. Assignment changes the current context, access
    returns the context-aware flag object, and deletion clears the override.
    """

    def __get__(self, obj: Database, objtype: type[Database]) -> ForceRollback:
        """Return the context-aware rollback flag for a database instance.

        Callers can coerce the returned object to ``bool`` or call it as a
        context manager. The descriptor deliberately exposes the same object so
        both interaction styles share one source of rollback state.
        """
        return obj._force_rollback

    def __set__(self, obj: Database, value: bool | None) -> None:
        """Set or reset the current context's rollback override.

        Attribute assignment remains supported for compatibility, but only
        booleans and ``None`` are valid because the value feeds transaction
        control directly.
        """
        assert value is None or isinstance(value, bool), f"Invalid type: {value!r}."
        obj._force_rollback.set(value)

    def __delete__(self, obj: Database) -> None:
        """Clear the current context's rollback override.

        Deleting the attribute does not remove the descriptor; it simply returns
        this task to the database's configured default rollback behavior.
        """
        obj._force_rollback.set(None)


class DatabaseURL:
    """Small URL helper backed by SQLAlchemy's ``URL`` parser.

    Saffier keeps this public helper for URL inspection, safe password masking,
    and test database URL rewriting, while relying on SQLAlchemy for canonical
    parsing and dialect resolution.
    """

    def __init__(self, url: str | DatabaseURL | URL | None = None) -> None:
        """Create a normalized public URL wrapper.

        ``DatabaseURL`` accepts strings, SQLAlchemy ``URL`` objects, and other
        ``DatabaseURL`` instances so callers can move between Saffier and
        SQLAlchemy APIs without losing password handling or test URL rewriting.
        """
        if isinstance(url, DatabaseURL):
            self._url = url._url
        elif isinstance(url, URL):
            self._url = url.render_as_string(hide_password=False)
        elif isinstance(url, str):
            self._url = url
        elif url is None:
            self._url = "invalid://localhost"
        else:
            raise TypeError(
                f"Invalid type for DatabaseURL. Expected str or DatabaseURL, got {type(url)}"
            )

    @cached_property
    def sqla_url(self) -> URL:
        """Return the parsed SQLAlchemy ``URL`` representation.

        Parsing is delegated to SQLAlchemy so dialect names, drivers, hosts, and
        query options follow SQLAlchemy 2.x rules. The value is cached because
        URL inspection happens often during registry and test-client setup.
        """
        return make_url(self._url)

    @cached_property
    def components(self) -> SplitResult:
        """Return split URL components with SQLite paths preserved.

        ``urllib.parse`` and SQLAlchemy render SQLite paths with subtly
        different slash counts. The normalization here keeps Saffier's historic
        ``DatabaseURL`` string behavior while still relying on SQLAlchemy for
        the initial parse.
        """
        components = urlsplit(self.sqla_url.render_as_string(hide_password=False))
        if components.path.startswith("///"):
            components = components._replace(path=f"//{components.path.lstrip('/')}")
        return components

    @classmethod
    def get_url(cls, splitted: SplitResult) -> str:
        """Reassemble a ``SplitResult`` into Saffier's URL string form.

        ``DatabaseURL.replace()`` works by modifying split components. This
        helper centralizes the final rendering step so path, query, and fragment
        handling stays identical across replacements and ``str(database_url)``.
        """
        url = f"{splitted.scheme}://{splitted.netloc or ''}{splitted.path}"
        if splitted.query:
            url = f"{url}?{splitted.query}"
        if splitted.fragment:
            url = f"{url}#{splitted.fragment}"
        return url

    @property
    def scheme(self) -> str:
        """Return the complete URL scheme.

        The scheme may include both a SQL dialect and driver, for example
        ``postgresql+asyncpg``. Saffier exposes it because migrations, tests,
        and diagnostics need to preserve that exact public value.
        """
        return self.components.scheme

    @property
    def dialect(self) -> str:
        """Return the SQLAlchemy dialect name from the URL scheme.

        Driver names are intentionally removed here so callers can branch on the
        database family, such as ``postgresql`` or ``sqlite``, without caring
        which async DBAPI driver was selected.
        """
        return self.scheme.split("+")[0]

    @property
    def driver(self) -> str | None:
        """Return the explicit SQLAlchemy driver name, when configured.

        URLs such as ``postgresql+asyncpg://`` expose ``asyncpg`` here, while
        plain dialect URLs return ``None``. Engine creation later fills in async
        defaults for common plain schemes.
        """
        scheme_parts = self.scheme.split("+", 1)
        if len(scheme_parts) == 1:
            return None
        return scheme_parts[1]

    @property
    def userinfo(self) -> bytes | None:
        """Return the percent-encoded user information segment.

        This mirrors the historical ``DatabaseURL`` API used by callers that
        need the raw authority credentials. Usernames and passwords are encoded
        separately so special characters are preserved safely.
        """
        if self.components.username:
            info = quote(self.components.username, safe="+")
            if self.password:
                info += ":" + quote(self.password, safe="+")
            return info.encode("utf-8")
        return None

    @property
    def username(self) -> str | None:
        """Return the decoded username component.

        SQLAlchemy keeps the parsed username available, and Saffier decodes it
        here so callers receive the same value they originally intended rather
        than percent-escaped text.
        """
        if self.components.username is None:
            return None
        return unquote(self.components.username)

    @property
    def password(self) -> str | None:
        """Return the decoded password component.

        The value is available for connection construction but is never used by
        ``repr()`` or ``obscure_password``. Those public renderers hide secrets
        while this property preserves explicit inspection behavior.
        """
        if self.components.password is None:
            return None
        return unquote(self.components.password)

    @property
    def hostname(self) -> str | None:
        """Return the network host or socket-style host option.

        Some database URLs place a Unix socket path in the query string instead
        of the hostname slot. This property keeps those connection strings
        usable by checking both locations.
        """
        host = self.components.hostname or self.options.get("host")
        if isinstance(host, list):
            return host[0] if host else None
        return host

    @property
    def port(self) -> int | None:
        """Return the parsed TCP port.

        SQLAlchemy and ``urllib`` validate the port during parsing, so callers
        receive either an integer port or ``None`` when the URL intentionally
        omits one.
        """
        return self.components.port

    @property
    def netloc(self) -> str | None:
        """Return the rendered network-location component.

        The value includes credentials, host, and port exactly as represented in
        the split URL. It is mostly used when reconstructing modified URLs.
        """
        return self.components.netloc

    @property
    def database(self) -> str:
        """Return the decoded database name from the URL path.

        Saffier treats the leading slash as URL structure rather than part of
        the database name. The remaining path is decoded so test database
        prefixes and DDL helpers operate on the logical database identifier.
        """
        path = self.components.path
        if path.startswith("/"):
            path = path[1:]
        return unquote(path)

    @cached_property
    def options(self) -> dict[str, str | list[str]]:
        """Return URL query parameters in Saffier's public option format.

        Single-value parameters are simplified to strings, while repeated
        parameters remain lists. ``Database`` later moves known engine options
        out of this mapping before passing the URL to SQLAlchemy.
        """
        result: dict[str, str | list[str]] = {}
        for key, value in parse_qs(self.components.query).items():
            result[key] = value[0] if len(value) == 1 else value
        return result

    def replace(self, **kwargs: Any) -> DatabaseURL:
        """Return a new URL with selected logical components replaced.

        The method accepts Saffier-friendly names such as ``database``,
        ``dialect``, ``driver``, ``username``, and ``options``. It rewrites the
        underlying split URL while preserving proper percent-encoding and
        leaving the original ``DatabaseURL`` immutable.
        """
        if (
            "username" in kwargs
            or "user" in kwargs
            or "password" in kwargs
            or "hostname" in kwargs
            or "host" in kwargs
            or "port" in kwargs
        ):
            hostname = kwargs.pop("hostname", kwargs.pop("host", self.hostname))
            port = kwargs.pop("port", self.port)
            username = kwargs.pop("username", kwargs.pop("user", self.components.username))
            password = kwargs.pop("password", self.components.password)

            netloc = hostname or ""
            if port is not None:
                netloc += f":{port}"
            if username is not None:
                userpass = quote(username, safe="+")
                if password is not None:
                    userpass += f":{quote(password, safe='+')}"
                netloc = f"{userpass}@{netloc}"

            kwargs["netloc"] = netloc

        if "database" in kwargs:
            database = kwargs.pop("database")
            kwargs["path"] = "" if database is None else f"/{database}"

        if "dialect" in kwargs or "driver" in kwargs:
            dialect = kwargs.pop("dialect", self.dialect)
            driver = kwargs.pop("driver", self.driver)
            kwargs["scheme"] = f"{dialect}+{driver}" if driver else dialect

        if not kwargs.get("netloc", self.netloc):
            kwargs["netloc"] = ""
        if "options" in kwargs:
            kwargs["query"] = urlencode(kwargs.pop("options"), doseq=True)

        components = self.components._replace(**kwargs)
        return self.__class__(self.get_url(components))

    @cached_property
    def obscure_password(self) -> str:
        """Return a string representation suitable for logs and repr output.

        Password masking is delegated to SQLAlchemy's URL renderer so the
        output follows SQLAlchemy's escaping rules while still protecting
        credentials from accidental disclosure.
        """
        return self.sqla_url.render_as_string(hide_password=True)

    def __str__(self) -> str:
        """Return the full public URL string.

        The string form intentionally preserves the clear password because it is
        used for actual connection setup. Use ``obscure_password`` or ``repr``
        when a safe diagnostic representation is needed.
        """
        return self.get_url(self.components)

    def __repr__(self) -> str:
        """Return a developer-facing representation with credentials hidden.

        The representation names the wrapper class and masks the password so
        debugging output can identify the target database without leaking
        secrets.
        """
        return f"{self.__class__.__name__}({self.obscure_password!r})"

    def __eq__(self, other: Any) -> bool:
        """Compare URL wrappers using their rendered public URL value.

        String values are first converted to ``DatabaseURL`` so equality works
        naturally in tests and public API code that compares raw configuration
        strings against parsed URL objects.
        """
        if isinstance(other, str):
            other = DatabaseURL(other)
        return str(self) == str(other)


_ACTIVE_CONNECTIONS: ContextVar[dict[int, tuple[AsyncConnection, ...]] | None] = ContextVar(
    "_ACTIVE_CONNECTIONS",
    default=None,
)
_LOOP_BOUND_DATABASES: ContextVar[tuple[int, ...]] = ContextVar(
    "_LOOP_BOUND_DATABASES",
    default=(),
)
_LOOP_BOUND_TOKEN_STACKS: ContextVar[dict[int, tuple[Token[tuple[int, ...]], ...]] | None] = (
    ContextVar(
        "_LOOP_BOUND_TOKEN_STACKS",
        default=None,
    )
)


def _active_connections() -> dict[int, tuple[AsyncConnection, ...]]:
    """Return the current context's transaction connection stacks.

    The context variable uses ``None`` as its default to avoid sharing a mutable
    dictionary between tasks. Callers receive an empty dictionary when no
    transaction has bound a SQLAlchemy connection in this context.
    """
    return _ACTIVE_CONNECTIONS.get() or {}


def _loop_bound_token_stacks() -> dict[int, tuple[Token[tuple[int, ...]], ...]]:
    """Return loop-bound marker tokens stored for the current context.

    Each task that enters a force-rollback database context owns its own token
    stack. Returning an empty dictionary for the unset state keeps the storage
    immutable-by-default and avoids cross-task token resets.
    """
    return _LOOP_BOUND_TOKEN_STACKS.get() or {}


def should_reenter_sync_bridge() -> bool:
    """Return whether sync code must stay on the current event loop.

    SQLAlchemy ``AsyncConnection`` objects and their asyncpg driver connections
    are loop-bound. The sync bridge uses this signal to avoid moving ORM lazy
    loads onto a helper loop while a transaction or force-rollback connection is
    active.
    """

    return bool(_active_connections() or _LOOP_BOUND_DATABASES.get())


class Transaction:
    """SQLAlchemy transaction context used by Saffier query and model APIs.

    A transaction binds Saffier execution helpers to one ``AsyncConnection`` in
    a context variable. Nested Saffier transactions use SQLAlchemy savepoints via
    ``begin_nested()``, and ``force_rollback`` always rolls back on exit.
    """

    def __init__(self, database: Database, force_rollback: bool = False, **kwargs: Any) -> None:
        """Prepare a transaction for a specific Saffier database.

        The transaction does not acquire a connection until ``start()`` or
        ``async with`` is used. This keeps construction cheap and lets decorator
        usage create a fresh SQLAlchemy transaction for each function call.
        """
        self.database = database
        self._force_rollback = force_rollback
        self._extra_options = kwargs
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None
        self._token: Token[dict[int, tuple[AsyncConnection, ...]] | None] | None = None
        self._owns_connection = False
        self._is_active = False

    async def __aenter__(self) -> Transaction:
        """Start the SQLAlchemy transaction for ``async with`` usage.

        Entering the context binds the selected ``AsyncConnection`` to Saffier's
        execution context so all ORM operations inside the block share the same
        SQLAlchemy transaction or savepoint.
        """
        await self.start(cleanup_on_error=False)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: Any = None,
    ) -> None:
        """Finish the transaction according to the context outcome.

        Exceptions and explicit ``force_rollback`` requests roll the underlying
        SQLAlchemy transaction back. A clean exit commits, matching the public
        Saffier transaction API while using SQLAlchemy's transaction object.
        """
        del exc_value, traceback
        if not self._is_active:
            return
        if exc_type is not None or self._force_rollback:
            await self.rollback()
        else:
            await self.commit()

    def __await__(self) -> Any:
        """Support manual transaction startup with ``await``.

        Some existing Saffier code awaits ``database.transaction()`` and then
        calls ``commit()`` or ``rollback()`` itself. Returning ``start()`` here
        preserves that public flow while still using native SQLAlchemy objects.
        """
        return self.start().__await__()

    def __call__(self, func: _CallableType) -> _CallableType:
        """Wrap an async callable in a fresh transaction.

        Decorator usage must not reuse the same ``Transaction`` instance across
        calls, because each invocation needs its own SQLAlchemy transaction
        lifecycle and context-variable binding.
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Execute the decorated coroutine inside its own transaction.

            A new transaction object is created for each call so concurrent
            invocations do not share SQLAlchemy transaction state or
            context-variable bindings.
            """
            async with self.__class__(
                self.database,
                force_rollback=self._force_rollback,
                **self._extra_options,
            ):
                return await func(*args, **kwargs)

        return cast("_CallableType", wrapper)

    async def start(self, cleanup_on_error: bool = True) -> Transaction:
        """Acquire a connection, begin a transaction, and bind it to the task.

        The method reuses an existing context-bound connection for nested
        transactions and uses ``begin_nested()`` when SQLAlchemy reports an
        active transaction. Otherwise it opens a new connection and begins a
        normal transaction directly through SQLAlchemy.
        """
        if self._is_active:
            raise RuntimeError("Transaction is already active")
        await self.database._ensure_connected()
        connection = await self.database._transaction_connection()
        self._connection = connection
        self._owns_connection = self.database._current_connection() is None and (
            not bool(self.database.force_rollback)
            or connection is not self.database._global_connection
        )
        try:
            await self._apply_transaction_options(connection)
            self._transaction = (
                await connection.begin_nested()
                if connection.in_transaction()
                else await connection.begin()
            )
            self._token = self.database._push_connection(connection)
            self._is_active = True
            return self
        except BaseException:
            if cleanup_on_error and self._owns_connection:
                await connection.close()
            self._connection = None
            self._owns_connection = False
            raise

    async def _apply_transaction_options(self, connection: AsyncConnection) -> None:
        """Apply SQLAlchemy execution options before transaction start.

        Isolation level changes must happen before ``begin()`` on SQLAlchemy
        connections. Nested transactions skip this step because the outer
        transaction already owns the connection-level options.
        """
        if connection.in_transaction():
            return
        options = dict(self._extra_options)
        if "isolation_level" not in options:
            options["isolation_level"] = "SERIALIZABLE"
        if options:
            await connection.execution_options(**options)

    async def _finish(self, action: str) -> None:
        """Finalize the active SQLAlchemy transaction and clean context state.

        The context-variable binding is reset even if commit or rollback raises.
        Connections opened by this transaction are closed, while connections
        inherited from an outer transaction or force-rollback context remain
        owned by that outer scope.
        """
        if not self._is_active or self._transaction is None:
            raise RuntimeError("Transaction is not active")
        transaction = self._transaction
        self._transaction = None
        self._is_active = False
        try:
            if action == "commit":
                await transaction.commit()
            else:
                await transaction.rollback()
        finally:
            if self._token is not None:
                _ACTIVE_CONNECTIONS.reset(self._token)
                self._token = None
            connection, self._connection = self._connection, None
            if self._owns_connection and connection is not None:
                await connection.close()
            self._owns_connection = False

    async def commit(self) -> None:
        """Commit the active SQLAlchemy transaction.

        Manual transaction users call this after ``await database.transaction()``.
        It delegates to the same cleanup path used by ``async with`` so context
        bindings and owned connections are released consistently.
        """
        await self._finish("commit")

    async def rollback(self) -> None:
        """Roll back the active SQLAlchemy transaction.

        This is used by explicit manual rollback, exception-driven context exit,
        and forced rollback scopes. Cleanup mirrors ``commit()`` so the database
        runtime does not retain stale context-bound connections.
        """
        await self._finish("rollback")


class Database:
    """Saffier database runtime backed directly by SQLAlchemy Async.

    The class owns an ``AsyncEngine``, an ``async_sessionmaker``, and execution
    helpers used by Saffier's ORM internals. Every database operation delegates
    to SQLAlchemy's public async engine, connection, transaction, and result
    APIs.
    """

    force_rollback = ForceRollbackDescriptor()
    default_batch_size: int = 100

    def __init__(
        self,
        url: str | DatabaseURL | URL | Database | None = None,
        *,
        force_rollback: bool | None = None,
        config: dict[str, Any] | None = None,
        full_isolation: bool | None = None,
        poll_interval: float | None = None,
        **options: Any,
    ) -> None:
        """Configure URL, engine options, and rollback behavior for the runtime.

        Engine creation is intentionally delayed until ``connect()`` so registry
        setup remains lightweight. Copy construction preserves the source
        database's URL and options while still creating independent SQLAlchemy
        engine and transaction state.
        """
        assert config is None or url is None, "Use either 'url' or 'config', not both."
        if isinstance(url, Database):
            assert not options, "Cannot specify options when copying a Database object."
            self.url = url.url
            self.options = dict(url.options)
            if force_rollback is None:
                force_rollback = bool(url.force_rollback)
            if full_isolation is None:
                full_isolation = url._full_isolation
            if poll_interval is None:
                poll_interval = url.poll_interval
        else:
            database_url = DatabaseURL(url)
            if config and "connection" in config:
                connection_config = config["connection"]
                if "credentials" in connection_config:
                    database_url = database_url.replace(**connection_config["credentials"])
            self.url, self.options = self._extract_options(database_url, **options)
            if force_rollback is None:
                force_rollback = False
            if full_isolation is None:
                full_isolation = False
            if poll_interval is None:
                poll_interval = 0.01

        self.poll_interval = poll_interval
        self._full_isolation = full_isolation
        self._force_rollback = ForceRollback(force_rollback)
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._global_connection: AsyncConnection | None = None
        self._global_transaction: AsyncTransaction | None = None
        self.is_connected = False
        self.ref_counter = 0
        self.ref_lock = asyncio.Lock()

    def __copy__(self) -> Database:
        """Return a new runtime object with the same configuration.

        The copy shares URL and option values but not live SQLAlchemy engines,
        connections, transactions, or context state. This is used by registry
        preparation paths that need an isolated runtime handle.
        """
        return self.__class__(self)

    @staticmethod
    def _extract_options(
        database_url: DatabaseURL,
        **options: Any,
    ) -> tuple[DatabaseURL, dict[str, Any]]:
        """Separate SQLAlchemy engine options from URL query parameters.

        Saffier accepts selected engine options in the URL for compatibility
        with existing configuration. Known values are removed from the URL and
        passed directly to ``create_async_engine()`` so SQLAlchemy owns pool,
        isolation, echo, and JSON behavior.
        """
        options.setdefault("pool_reset_on_return", None)
        options.setdefault("json_serializer", _json_serializer)
        options.setdefault("json_deserializer", _json_deserializer)
        query_options = dict(database_url.options)
        for param in ("ssl", "echo", "echo_pool"):
            if param in query_options:
                assert param not in options
                value = cast("str", query_options.pop(param))
                options[param] = value.lower() in {"true", ""}
        if "isolation_level" in query_options:
            assert "isolation_level" not in options
            options["isolation_level"] = cast("str", query_options.pop("isolation_level"))
        for param in ("pool_size", "max_overflow"):
            if param in query_options:
                assert param not in options
                options[param] = int(cast("str", query_options.pop(param)))
        if "pool_recycle" in query_options:
            assert "pool_recycle" not in options
            options["pool_recycle"] = float(cast("str", query_options.pop("pool_recycle")))
        options.setdefault("isolation_level", "AUTOCOMMIT")
        return database_url.replace(options=query_options), options

    @property
    def engine(self) -> AsyncEngine | None:
        """Return the live SQLAlchemy async engine, when connected.

        The property exposes the native ``AsyncEngine`` for advanced callers
        without manufacturing another abstraction. ``None`` means lifecycle has
        not connected the database yet or has already disconnected it.
        """
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession] | None:
        """Return the SQLAlchemy async session factory, when available.

        Saffier creates this with ``async_sessionmaker`` beside the engine.
        Returning ``None`` before connection makes lifecycle state explicit
        rather than constructing a hidden engine on property access.
        """
        return self._sessionmaker

    async def session(self) -> AsyncSession:
        """Create a native SQLAlchemy ``AsyncSession``.

        The database must be connected so the session factory is bound to the
        current ``AsyncEngine``. Sessions use ``expire_on_commit=False`` to keep
        ORM-facing values usable after transaction boundaries.
        """
        await self._ensure_connected()
        assert self._sessionmaker is not None
        return self._sessionmaker()

    async def connect_hook(self) -> None:
        """Run subclass setup before the SQLAlchemy engine is created.

        ``DatabaseTestClient`` uses this hook to create or verify the test
        database before normal connection proceeds. The base implementation is
        intentionally empty so regular runtimes connect directly.
        """
        pass

    async def disconnect_hook(self) -> None:
        """Run subclass cleanup after the SQLAlchemy engine is disposed.

        Hooks run after Saffier has closed its force-rollback transaction and
        disposed the engine, which lets test clients safely drop databases or
        release resources outside the live connection pool.
        """
        pass

    async def connect(self) -> bool:
        """Create the SQLAlchemy async engine for this database lifecycle.

        Connection is reference-counted because registries and nested async
        contexts may ask for the same database to connect more than once. The
        first caller creates ``AsyncEngine`` and ``async_sessionmaker``; later
        callers reuse that live SQLAlchemy runtime.
        """
        async with self.ref_lock:
            self.ref_counter += 1
            if self.ref_counter > 1:
                if bool(self.force_rollback):
                    await self._ensure_global_force_rollback()
                return False
            try:
                await self.connect_hook()
                self._engine = create_async_engine(_async_url(self.url), **self.options)
                self._sessionmaker = async_sessionmaker(
                    self._engine,
                    expire_on_commit=False,
                )
                self.is_connected = True
                if bool(self.force_rollback):
                    await self._ensure_global_force_rollback()
            except BaseException:
                self.ref_counter = 0
                self.is_connected = False
                self._engine = None
                self._sessionmaker = None
                raise
            return True

    async def disconnect(self, force: bool = False) -> bool:
        """Dispose the SQLAlchemy async engine when lifecycle ownership ends.

        Normal disconnect decrements the reference counter and only disposes the
        engine for the last owner. ``force=True`` is reserved for teardown paths
        that must close the pool regardless of outstanding references.
        """
        async with self.ref_lock:
            if force:
                self.ref_counter = 0
            elif self.ref_counter > 0:
                self.ref_counter -= 1
            if self.ref_counter > 0:
                return False
            if not self.is_connected:
                return False
            try:
                await self._close_global_force_rollback()
            finally:
                engine, self._engine = self._engine, None
                self._sessionmaker = None
                self.is_connected = False
                if engine is not None:
                    await engine.dispose(close=True)
                await self.disconnect_hook()
            return True

    async def __aenter__(self) -> Database:
        """Connect the database for ``async with`` lifecycle management.

        When forced rollback is active, the database is also marked as
        loop-bound so synchronous lazy-loading bridges re-enter the owning event
        loop instead of moving SQLAlchemy connections to a helper loop.
        """
        await self.connect()
        if bool(self.force_rollback):
            self._push_loop_bound_database()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: Any = None,
    ) -> None:
        """Disconnect the database at the end of an async context.

        Any loop-bound marker installed for force-rollback mode is removed
        before the lifecycle reference is released, keeping subsequent sync
        bridge calls free to use the normal helper-loop path.
        """
        del exc_type, exc_value, traceback
        self._pop_loop_bound_database()
        await self.disconnect()

    async def _ensure_connected(self) -> None:
        """Validate that the database has an active SQLAlchemy engine.

        Execution helpers call this before reaching for ``AsyncEngine``. Raising
        here gives callers a clear lifecycle error instead of a later attribute
        failure on a missing connection pool.
        """
        if not self.is_connected or self._engine is None:
            raise RuntimeError("Database is not connected")

    def _current_connection(self) -> AsyncConnection | None:
        """Return the connection currently bound to this execution context.

        Transaction contexts take precedence because nested operations must use
        the same SQLAlchemy connection. If no transaction is active and forced
        rollback is enabled, the reusable rollback connection becomes the
        current connection for test isolation.
        """
        stack = _active_connections().get(id(self), ())
        if stack:
            return stack[-1]
        if bool(self.force_rollback):
            return self._global_connection
        return None

    def _push_connection(
        self,
        connection: AsyncConnection,
    ) -> Token[dict[int, tuple[AsyncConnection, ...]] | None]:
        """Bind a SQLAlchemy connection to this database in the current context.

        Bindings are stored as a per-database stack so nested transactions can
        push savepoint connections and then restore the previous state exactly
        when they finish.
        """
        connections = _active_connections()
        copied = dict(connections)
        copied[id(self)] = (*copied.get(id(self), ()), connection)
        return _ACTIVE_CONNECTIONS.set(copied)

    def _push_loop_bound_database(self) -> None:
        """Mark this database as using loop-bound SQLAlchemy resources.

        Force-rollback mode keeps one SQLAlchemy connection open across many ORM
        operations. The sync bridge reads this marker to avoid executing lazy
        loads on a different event loop from that connection.
        """
        databases = _LOOP_BOUND_DATABASES.get()
        token = _LOOP_BOUND_DATABASES.set((*databases, id(self)))
        token_stacks = dict(_loop_bound_token_stacks())
        token_stacks[id(self)] = (*token_stacks.get(id(self), ()), token)
        _LOOP_BOUND_TOKEN_STACKS.set(token_stacks)

    def _pop_loop_bound_database(self) -> None:
        """Remove this database's loop-bound marker for the current context.

        The marker token must be reset in the same context that created it.
        Keeping the stack in a context variable prevents concurrent tasks using
        the same ``Database`` instance from popping and resetting each other's
        SQLAlchemy loop markers.
        """
        token_stacks = _loop_bound_token_stacks()
        stack = token_stacks.get(id(self), ())
        if not stack:
            return
        token = stack[-1]
        copied = dict(token_stacks)
        if len(stack) == 1:
            copied.pop(id(self), None)
        else:
            copied[id(self)] = stack[:-1]
        _LOOP_BOUND_TOKEN_STACKS.set(copied)
        _LOOP_BOUND_DATABASES.reset(token)

    async def _ensure_global_force_rollback(self) -> AsyncConnection:
        """Open the reusable rollback transaction used for test isolation.

        The connection and transaction are created directly through SQLAlchemy
        and held for the database lifecycle. ORM statements run against this
        connection, and disconnect rolls the outer transaction back.
        """
        await self._ensure_connected()
        if self._global_connection is not None:
            return self._global_connection
        assert self._engine is not None
        connection = await self._engine.connect()
        await connection.execution_options(isolation_level="SERIALIZABLE")
        transaction = await connection.begin()
        self._global_connection = connection
        self._global_transaction = transaction
        return connection

    async def _close_global_force_rollback(self) -> None:
        """Roll back and close the force-rollback connection.

        Teardown suppresses rollback errors so disposal can still close the
        underlying SQLAlchemy connection. This mirrors test cleanup expectations
        where isolation should be best-effort during exceptional shutdown.
        """
        transaction, self._global_transaction = self._global_transaction, None
        connection, self._global_connection = self._global_connection, None
        try:
            if transaction is not None:
                with contextlib.suppress(Exception):
                    await transaction.rollback()
        finally:
            if connection is not None:
                await connection.close()

    async def _transaction_connection(self) -> AsyncConnection:
        """Choose the SQLAlchemy connection for a new transaction scope.

        Existing context connections are reused for nesting, forced rollback
        scopes reuse the lifecycle-wide rollback connection, and ordinary
        transactions open a fresh connection from the async engine's pool.
        """
        current = self._current_connection()
        if current is not None:
            return current
        if bool(self.force_rollback):
            return await self._ensure_global_force_rollback()
        await self._ensure_connected()
        assert self._engine is not None
        return await self._engine.connect()

    @contextlib.asynccontextmanager
    async def connection(self) -> AsyncGenerator[AsyncConnection, None]:
        """Yield a raw SQLAlchemy ``AsyncConnection`` for direct operations.

        The yielded connection is the current transaction-bound connection when
        one exists; otherwise a short-lived connection is opened from the
        ``AsyncEngine`` pool. This keeps direct SQLAlchemy usage aligned with
        Saffier's transaction context instead of bypassing it.
        """
        current = self._current_connection()
        if current is not None:
            yield current
            return
        await self._ensure_connected()
        assert self._engine is not None
        async with self._engine.connect() as connection:
            yield connection

    @contextlib.asynccontextmanager
    async def _execution_connection(self) -> AsyncGenerator[AsyncConnection, None]:
        """Yield the SQLAlchemy connection for one ORM execution helper.

        ORM helpers should not decide whether they are inside a transaction,
        forced rollback block, or normal engine checkout. This helper centralizes
        that choice so fetch, execute, and iteration paths all share the same
        connection ownership rules.
        """
        current = self._current_connection()
        if current is not None:
            yield current
            return
        async with self.connection() as connection:
            yield connection

    async def fetch_all(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[sqlalchemy.Row[Any]]:
        """Execute a statement and return all rows from SQLAlchemy.

        The method preserves Saffier's public ``fetch_all`` API while routing
        execution directly through ``AsyncConnection.execute()``. Results are
        materialized before the cursor is closed so callers can inspect rows
        after the connection context exits.
        """
        del timeout
        statement = _coerce_statement(query)
        async with self._execution_connection() as connection:
            result = await connection.execute(statement, values or {})
            try:
                return list(result.fetchall())
            finally:
                result.close()

    async def fetch_one(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: dict[str, Any] | None = None,
        pos: int = 0,
        timeout: float | None = None,
    ) -> sqlalchemy.Row[Any] | None:
        """Execute a statement and return one row by logical position.

        Positive positions are translated into SQLAlchemy ``offset`` and
        ``limit`` calls when the statement supports them. ``-1`` keeps the
        historic "last row" behavior by materializing the result and returning
        the final entry.
        """
        del timeout
        statement = _coerce_statement(query)
        if pos > 0 and hasattr(statement, "offset"):
            statement = statement.offset(pos)  # type: ignore[assignment,union-attr]
        if pos >= 0 and hasattr(statement, "limit"):
            statement = statement.limit(1)  # type: ignore[assignment,union-attr]
        rows = await self.fetch_all(statement, values)
        if not rows:
            return None
        if pos == -1:
            return rows[-1]
        if pos < -1:
            raise NotImplementedError(
                f"Only positive numbers and -1 for the last result are currently supported: {pos}"
            )
        return rows[0]

    async def fetch_val(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: dict[str, Any] | None = None,
        column: int | str = 0,
        pos: int = 0,
        timeout: float | None = None,
    ) -> Any:
        """Execute a statement and return a single value from one row.

        The value can be selected by integer position or by row mapping key.
        Returning ``None`` for empty results matches the existing Saffier query
        helper contract.
        """
        row = await self.fetch_one(query, values, pos=pos, timeout=timeout)
        if row is None:
            return None
        if isinstance(column, str):
            return row._mapping[column]
        return row[column]

    @staticmethod
    def _parse_execute_result(result: sqlalchemy.CursorResult[Any]) -> Any:
        """Convert SQLAlchemy cursor metadata into Saffier's execute result.

        Inserts historically return primary-key metadata when the dialect can
        provide it, while updates and deletes return ``rowcount``. Keeping this
        translation in one helper lets ``execute()`` stay SQLAlchemy-native
        without leaking dialect-specific cursor details throughout the ORM.
        """
        if result.is_insert:
            with contextlib.suppress(AttributeError):
                inserted_primary_key = result.inserted_primary_key
                if inserted_primary_key:
                    return inserted_primary_key
            with contextlib.suppress(AttributeError):
                return result.lastrowid
        return result.rowcount

    async def execute(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: Any = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute one SQLAlchemy statement and return the public result value.

        Statements are run through the current execution connection, which means
        they participate in active Saffier transactions and force-rollback test
        contexts. The returned value follows the legacy Saffier contract:
        insert metadata when available, otherwise affected row count.
        """
        del timeout
        statement = _coerce_statement(query)
        async with self._execution_connection() as connection:
            result = (
                await connection.execute(statement, values)
                if values is not None
                else await connection.execute(statement)
            )
            try:
                return self._parse_execute_result(result)
            finally:
                result.close()

    async def execute_many(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: Any = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute one statement against many parameter dictionaries.

        SQLAlchemy handles executemany behavior when a sequence of parameter
        dictionaries is passed to ``execute()``. Saffier only adapts the cursor
        metadata back into the value expected by bulk insert and update code.
        """
        del timeout
        statement = _coerce_statement(query)
        async with self._execution_connection() as connection:
            result = (
                await connection.execute(statement, values)
                if values is not None
                else await connection.execute(statement)
            )
            try:
                if result.is_insert:
                    with contextlib.suppress(AttributeError):
                        if result.inserted_primary_key_rows is not None:
                            return result.inserted_primary_key_rows
                return result.rowcount
            finally:
                result.close()

    async def iterate(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: dict[str, Any] | None = None,
        chunk_size: int | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[sqlalchemy.Row[Any], None]:
        """Yield rows from a SQLAlchemy statement without hiding result objects.

        Dialects with server-side cursor support use ``AsyncConnection.stream``
        and ``yield_per`` when a transaction is already active. Dialects without
        streaming support, or autocommit connections where asyncpg cannot open a
        cursor, fall back to a materialized result while preserving the async
        generator API.
        """
        del timeout
        statement = _coerce_statement(query)
        chunk_size = chunk_size or self.default_batch_size
        async with self._execution_connection() as connection:
            if (
                not connection.dialect.supports_server_side_cursors
                or not connection.in_transaction()
            ):
                result = await connection.execute(statement, values or {})
                try:
                    for row in result.fetchall():
                        yield row
                finally:
                    result.close()
                return

            await connection.execution_options(yield_per=chunk_size)
            try:
                async with connection.stream(statement, values or {}) as result:
                    async for row in result:
                        yield row
            finally:
                await connection.execution_options(yield_per=0)

    async def batched_iterate(
        self,
        query: sqlalchemy.ClauseElement | str,
        values: dict[str, Any] | None = None,
        batch_size: int | None = None,
        batch_wrapper: Callable[[Sequence[Any]], Any] = tuple,
        timeout: float | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Yield result rows grouped into caller-configured batches.

        This compatibility helper materializes rows with ``fetch_all`` and then
        wraps each batch with ``batch_wrapper``. The execution itself still uses
        SQLAlchemy async connections and participates in active transactions.
        """
        del timeout
        batch_size = batch_size or self.default_batch_size
        rows = await self.fetch_all(query, values)
        for batch in _batch_rows(rows, batch_size):
            yield batch_wrapper(batch)

    def transaction(self, *, force_rollback: bool = False, **kwargs: Any) -> Transaction:
        """Create a SQLAlchemy-backed Saffier transaction context.

        Keyword arguments are passed through as SQLAlchemy execution options
        before the transaction begins. The returned object supports ``async
        with``, manual ``await`` startup, and decorator usage.
        """
        return Transaction(self, force_rollback=force_rollback, **kwargs)

    async def run_sync(
        self,
        fn: Callable[..., Any],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run a synchronous SQLAlchemy callable against an async connection.

        SQLAlchemy exposes ``AsyncConnection.run_sync()`` for operations such as
        metadata creation and reflection that still use synchronous Core APIs.
        Saffier forwards directly to that method so schema helpers remain
        idiomatic SQLAlchemy 2.x async code.
        """
        del timeout
        async with self._execution_connection() as connection:
            return await connection.run_sync(fn, *args, **kwargs)

    async def create_all(
        self,
        meta: sqlalchemy.MetaData,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Create every table in a SQLAlchemy ``MetaData`` object.

        Table creation is executed through ``AsyncConnection.run_sync()`` so the
        synchronous ``MetaData.create_all`` API runs on the connection paired
        with the active async engine or transaction.
        """
        del timeout
        await self.run_sync(meta.create_all, **kwargs)

    async def drop_all(
        self,
        meta: sqlalchemy.MetaData,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Drop every table in a SQLAlchemy ``MetaData`` object.

        The method mirrors ``create_all`` and keeps Saffier schema teardown on
        SQLAlchemy's public metadata API. Any active transaction or
        force-rollback connection is respected by the execution connection.
        """
        del timeout
        await self.run_sync(meta.drop_all, **kwargs)

    def asgi(
        self,
        app: ASGIApp | None = None,
        handle_lifespan: bool = False,
    ) -> ASGIApp | Callable[[ASGIApp], ASGIApp]:
        """Wrap an ASGI application with SQLAlchemy engine lifecycle hooks.

        The wrapper connects the database during ASGI startup and registers
        ``disconnect`` as cleanup. This keeps framework integration small while
        still ensuring SQLAlchemy pools are opened and disposed at application
        lifecycle boundaries.
        """
        if LifespanHook is None:
            raise RuntimeError("monkay.asgi is required for ASGI integration.")

        async def setup() -> contextlib.AsyncExitStack:
            """Connect the database and register ASGI lifespan cleanup.

            ``LifespanHook`` expects a stack-like object that owns async cleanup
            callbacks. Saffier connects the SQLAlchemy engine first and then
            pushes ``disconnect`` so pool disposal always runs on shutdown.
            """
            cleanupstack = contextlib.AsyncExitStack()
            await self.connect()
            cleanupstack.push_async_callback(self.disconnect)
            return cleanupstack

        return LifespanHook(app, setup=setup, do_forward=not handle_lifespan)


class DatabaseTestClient(Database):
    """Testing database runtime built directly on SQLAlchemy Async.

    The client rewrites the configured database name with a test prefix and can
    create, reuse, or drop that database for test runs. It inherits the normal
    SQLAlchemy-backed ``Database`` execution and transaction behavior.
    """

    testclient_operation_timeout: float = 4
    testclient_operation_timeout_init: float = 8
    testclient_default_full_isolation: bool = True
    testclient_default_force_rollback: bool = False
    testclient_default_lazy_setup: bool = False
    testclient_default_use_existing: bool = False
    testclient_default_drop_database: bool = False
    testclient_default_test_prefix: str = "test_"

    def __init__(
        self,
        url: str | DatabaseURL | URL | Database | None = None,
        *,
        force_rollback: bool | None = None,
        full_isolation: bool | None = None,
        use_existing: bool | None = None,
        drop_database: bool | None = None,
        lazy_setup: bool | None = None,
        test_prefix: str | None = None,
        **options: Any,
    ) -> None:
        """Prepare the test database URL and setup policy.

        The client rewrites the target database name with the configured test
        prefix unless an empty prefix is requested. Setup may run immediately in
        synchronous construction contexts or be deferred to ``connect()`` when
        construction happens inside an event loop.
        """
        if use_existing is None:
            use_existing = self.testclient_default_use_existing
        if drop_database is None:
            drop_database = self.testclient_default_drop_database
        if full_isolation is None:
            full_isolation = self.testclient_default_full_isolation
        if test_prefix is None:
            test_prefix = self.testclient_default_test_prefix
        if force_rollback is None:
            force_rollback = self.testclient_default_force_rollback
        if lazy_setup is None:
            lazy_setup = self.testclient_default_lazy_setup

        self.use_existing = use_existing
        self.drop = drop_database
        self._setup_executed_init = False

        source_database = url if isinstance(url, Database) else None
        super().__init__(
            url,
            force_rollback=force_rollback,
            full_isolation=full_isolation,
            **options,
        )
        if source_database is not None and hasattr(source_database, "test_db_url"):
            self.test_db_url = source_database.test_db_url
        else:
            if test_prefix:
                self.url = self.url.replace(database=f"{test_prefix}{self.url.database}")
            self.test_db_url = str(self.url)

        if not lazy_setup:
            self.setup_protected(self.testclient_operation_timeout_init)
            self._setup_executed_init = True

    async def setup(self) -> None:
        """Create or refresh the configured test database.

        Existing databases are dropped unless ``use_existing`` is enabled. All
        create/drop work goes through SQLAlchemy async connections so the test
        client no longer relies on an external database utility layer.
        """
        db_exists = await self.database_exists(self.test_db_url)
        if not self.use_existing:
            try:
                if db_exists:
                    await self.drop_database(self.test_db_url)
                await self.create_database(self.test_db_url)
            except (ProgrammingError, OperationalError, TypeError):
                self.drop = False
        elif not db_exists:
            try:
                await self.create_database(self.test_db_url)
            except (ProgrammingError, OperationalError):
                self.drop = False

    def setup_protected(self, operation_timeout: float) -> None:
        """Run constructor-time setup only when it is legal to block.

        Some tests instantiate the client at module import time, where no event
        loop is running and ``asyncio.run`` is safe. If construction happens
        inside a running loop, setup is deferred to ``connect_hook`` so callers
        do not hit nested-loop errors.
        """
        del operation_timeout
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            with contextlib.suppress(TimeoutError):
                asyncio.run(self.setup())
        else:
            # Constructors can be called from an async test module. Defer setup
            # to connect() where awaiting is legal.
            return

    async def connect_hook(self) -> None:
        """Ensure lazy test database setup has run before engine creation.

        ``Database.connect()`` calls this hook immediately before creating the
        SQLAlchemy ``AsyncEngine``. Running setup here guarantees the target
        database exists before the pool attempts its first connection.
        """
        if not self._setup_executed_init:
            await self.setup()
            self._setup_executed_init = True
        await super().connect_hook()

    async def disconnect_hook(self) -> None:
        """Drop the test database after the SQLAlchemy engine is disposed.

        Dropping happens after disconnect so no pooled SQLAlchemy connections
        remain open against the database being removed. The setup flag is reset
        so a later reconnect can recreate or verify the database again.
        """
        self._setup_executed_init = False
        if self.drop:
            await self.drop_database(self.test_db_url)
        await super().disconnect_hook()

    async def is_database_exist(self) -> Any:
        """Return whether this client's configured test database exists.

        The method keeps the historical public spelling while delegating to the
        SQLAlchemy-native class-level probe. It is useful for tests that assert
        setup and teardown behavior directly.
        """
        return await self.database_exists(self.test_db_url)

    @classmethod
    async def database_exists(cls, url: str | URL | DatabaseURL) -> bool:
        """Check database existence using SQLAlchemy async connections.

        SQLite is checked through the filesystem because a missing file is the
        database state. PostgreSQL and MySQL probe administrative catalogs from
        fallback databases so the target database can be checked even when it
        does not yet accept connections.
        """
        database_url = url if isinstance(url, DatabaseURL) else DatabaseURL(url)
        database = database_url.database
        dialect_name = database_url.sqla_url.get_dialect(True).name
        if dialect_name == "sqlite":
            return not database or database == ":memory:" or os.path.exists(database)

        if dialect_name == "postgresql":
            text = sqlalchemy.text("SELECT 1 FROM pg_database WHERE datname=:database")
            for candidate in (database, "postgres", "template1", "template0", None):
                try:
                    probe_url = database_url.replace(database=candidate)
                    async with Database(
                        probe_url, force_rollback=False, full_isolation=False
                    ) as db:
                        statement = sqlalchemy.text("SELECT 1") if candidate == database else text
                        values = None if candidate == database else {"database": database}
                        if await db.fetch_val(statement, values):
                            return True
                except Exception:
                    pass
            return False

        if dialect_name == "mysql":
            text = sqlalchemy.text(
                "SELECT 1 FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = :database"
            )
            for candidate in (database, None, "mysql"):
                try:
                    probe_url = database_url.replace(database=candidate)
                    async with Database(
                        probe_url, force_rollback=False, full_isolation=False
                    ) as db:
                        statement = sqlalchemy.text("SELECT 1") if candidate == database else text
                        values = None if candidate == database else {"database": database}
                        if await db.fetch_val(statement, values):
                            return True
                except Exception:
                    pass
            return False

        try:
            async with Database(database_url, force_rollback=False, full_isolation=False) as db:
                await db.fetch_val(sqlalchemy.text("SELECT 1"))
                return True
        except Exception:
            return False

    @classmethod
    def _resolve_admin_url(cls, url: str | URL | DatabaseURL) -> tuple[DatabaseURL, str, str, str]:
        """Resolve the administrative connection target for database DDL.

        Creating or dropping a database usually cannot be done while connected
        to that same database. This helper returns a SQLAlchemy-compatible URL
        for the dialect's administrative database, the original database name,
        and dialect metadata used by create/drop helpers.
        """
        database_url = url if isinstance(url, DatabaseURL) else DatabaseURL(url)
        database = database_url.database
        dialect = database_url.sqla_url.get_dialect(True)
        dialect_name = dialect.name
        dialect_driver = dialect.driver
        if dialect_name == "postgresql":
            database_url = database_url.replace(database="postgres")
        elif dialect_name == "mssql":
            database_url = database_url.replace(database="master")
        elif dialect_name == "cockroachdb":
            database_url = database_url.replace(database="defaultdb")
        elif dialect_name != "sqlite":
            database_url = database_url.replace(database=None)
        return database_url, database, dialect_name, dialect_driver

    @staticmethod
    def _sanitize_charset_name(value: str) -> str:
        """Validate an encoding identifier before it is interpolated into DDL.

        SQLAlchemy bind parameters cannot represent identifiers or charset names
        in all dialect DDL forms. Restricting the value to alphanumerics and
        underscores prevents crafted input from becoming executable SQL.
        """
        if not re.fullmatch(r"[A-Za-z0-9_]+", value):
            raise ValueError(f"Invalid encoding name: {value!r}")
        return value

    @staticmethod
    def _quote_identifier(connection: AsyncConnection, identifier: str) -> str:
        """Quote a database identifier with the active SQLAlchemy dialect.

        Database names are identifiers, not values, so they cannot be safely
        passed as bind parameters in ``CREATE DATABASE`` or ``DROP DATABASE``.
        SQLAlchemy's dialect preparer supplies the correct quoting rules for
        the live connection.
        """
        return connection.sync_connection.dialect.identifier_preparer.quote(identifier)

    @classmethod
    async def create_database(
        cls,
        url: str | URL | DatabaseURL,
        encoding: str = "utf8",
        template: str | None = None,
    ) -> None:
        """Create a database through dialect-appropriate SQLAlchemy DDL.

        The method connects to an administrative database resolved from the
        target URL, quotes identifiers through SQLAlchemy, and emits the minimum
        dialect-specific DDL needed for PostgreSQL, MySQL, SQLite, and generic
        SQLAlchemy-supported databases.
        """
        database_url, database, dialect_name, _ = cls._resolve_admin_url(url)
        if dialect_name == "sqlite":
            if database and database != ":memory:":
                async with Database(
                    database_url, force_rollback=False, full_isolation=False
                ) as db:
                    await db.execute(sqlalchemy.text("CREATE TABLE _dropme_DB(id int)"))
                    await db.execute(sqlalchemy.text("DROP TABLE _dropme_DB"))
            return

        async with (
            Database(database_url, force_rollback=False, full_isolation=False) as db,
            db.connection() as connection,
        ):
            quote = cls._quote_identifier(connection, database)
            if dialect_name == "postgresql":
                encoding = cls._sanitize_charset_name(encoding)
                template = template or "template1"
                template = cls._quote_identifier(connection, template)
                await connection.execute(
                    sqlalchemy.text(
                        f"CREATE DATABASE {quote} ENCODING '{encoding}' TEMPLATE {template}"
                    )
                )
            elif dialect_name == "mysql":
                encoding = cls._sanitize_charset_name(encoding)
                await connection.execute(
                    sqlalchemy.text(f"CREATE DATABASE {quote} CHARACTER SET {encoding}")
                )
            else:
                await connection.execute(sqlalchemy.text(f"CREATE DATABASE {quote}"))

    @classmethod
    async def drop_database(
        cls,
        url: str | URL | DatabaseURL,
        *,
        use_if_exists: bool = True,
    ) -> None:
        """Drop a database through dialect-appropriate SQLAlchemy DDL.

        SQLite teardown removes the database file. PostgreSQL teardown first
        terminates other sessions connected to the target database before
        issuing ``DROP DATABASE`` from an administrative connection.
        """
        database_url, database, dialect_name, _ = cls._resolve_admin_url(url)
        if dialect_name == "sqlite":
            if database and database != ":memory:":
                with contextlib.suppress(FileNotFoundError):
                    os.remove(database)
            return

        exists_text = "IF EXISTS " if use_if_exists else ""
        async with (
            Database(database_url, force_rollback=False, full_isolation=False) as db,
            db.connection() as connection,
        ):
            quote = cls._quote_identifier(connection, database)
            if dialect_name.startswith("postgres"):
                server_version = cast(
                    str,
                    await db.fetch_val(
                        sqlalchemy.text(
                            "SELECT setting FROM pg_settings WHERE name = 'server_version'"
                        )
                    ),
                ).split(" ")[0]
                version = tuple(map(int, server_version.split(".")[:2]))
                pid_column = "pid" if version >= (9, 2) else "procpid"
                await connection.execute(
                    sqlalchemy.text(
                        f"""
                        SELECT pg_terminate_backend(pg_stat_activity.{pid_column})
                        FROM pg_stat_activity
                        WHERE pg_stat_activity.datname = :database
                        AND {pid_column} <> pg_backend_pid()
                        """
                    ),
                    {"database": database},
                )
            with contextlib.suppress(ProgrammingError):
                await connection.execute(sqlalchemy.text(f"DROP DATABASE {exists_text}{quote}"))


SaffierTestClient = DatabaseTestClient

__all__ = [
    "ACTIVE_FORCE_ROLLBACKS",
    "Database",
    "DatabaseTestClient",
    "DatabaseURL",
    "ForceRollback",
    "SaffierTestClient",
    "Transaction",
    "should_reenter_sync_bridge",
]
