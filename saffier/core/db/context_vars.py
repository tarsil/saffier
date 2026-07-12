from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from saffier import Database, Model, QuerySet

TENANT: ContextVar[str] = ContextVar("tenant", default=None)
SHEMA: ContextVar[str] = ContextVar("SHEMA", default=None)
CURRENT_FIELD_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("CURRENT_FIELD_CONTEXT")
CURRENT_INSTANCE: ContextVar[Any | None] = ContextVar("CURRENT_INSTANCE", default=None)
CURRENT_MODEL_INSTANCE: ContextVar[Any | None] = ContextVar("CURRENT_MODEL_INSTANCE", default=None)
CURRENT_PHASE: ContextVar[str] = ContextVar("CURRENT_PHASE", default="")
EXPLICIT_SPECIFIED_VALUES: ContextVar[set[str] | None] = ContextVar(
    "EXPLICIT_SPECIFIED_VALUES",
    default=None,
)


def get_tenant() -> str | None:
    """Return the tenant schema bound to the current async context.

    Query construction and registry helpers consult this value to decide which
    tenant schema should take precedence when multi-tenancy is enabled.
    """
    return TENANT.get()


def set_tenant(value: str | None) -> None:
    """Set the active tenant schema for the current context.

    When a tenant is set, queryset helpers prefer it over the plain schema
    context variable.
    """
    TENANT.set(value)


@contextmanager
def with_tenant(tenant: str | None) -> Generator[None, None, None]:
    """Temporarily bind a tenant schema to the current context.

    Multi-tenant request handling should prefer this context manager over a
    plain ``set_tenant`` call because it restores the previous tenant
    automatically when the request, job, or test block finishes. A tenant value
    takes precedence over the plain schema context for the duration of the
    block, matching how tenant-scoped querysets are resolved.

    Args:
        tenant: Tenant schema to make active, or ``None`` to temporarily clear
            tenant routing inside the block.

    Yields:
        None: Control while the tenant binding is active.
    """
    token = TENANT.set(tenant)
    try:
        yield
    finally:
        TENANT.reset(token)


def get_schema() -> str | None:
    """Return the effective schema for the current context.

    Tenant routing has priority over plain schema routing. This lets
    ``with_tenant`` safely wrap request handling without leaking into the
    lower-priority ``with_schema`` helper.

    Returns:
        str | None: Active tenant schema, active plain schema, or ``None``.
    """
    return TENANT.get() or SHEMA.get()


def set_schema(value: str | None) -> None:
    """Set the plain schema context for subsequent queryset construction.

    Args:
        value: Schema name to bind, or ``None`` to clear the plain schema
            context. Tenant context, when present, still takes precedence.
    """
    SHEMA.set(value)


def set_queryset_schema(
    queryset: "QuerySet",
    model_class: type["Model"],
    value: str | None,
) -> "QuerySet":
    """Return a queryset rebound to a specific schema.

    Args:
        queryset: Source queryset being cloned.
        model_class: Model class targeted by the queryset.
        value: Schema name to bind.

    Returns:
        QuerySet: Schema-bound queryset clone.
    """
    return queryset.__class__(
        model_class=model_class,
        using_schema=value,
        table=model_class.table_schema(value),
    )


def set_queryset_database(
    queryset: "QuerySet",
    model_class: type["Model"],
    database: type["Database"],
    schema: str | None = None,
) -> "QuerySet":
    """Return a queryset rebound to a specific database and optional schema.

    Args:
        queryset: Source queryset being cloned.
        model_class: Model class targeted by the queryset.
        database: Database object to bind.
        schema: Optional schema override.

    Returns:
        QuerySet: Database-bound queryset clone.
    """
    if not schema:
        return queryset.__class__(
            model_class=model_class,
            database=database,
            table=model_class.table_schema(schema),
        )
    return queryset.__class__(model_class=model_class, database=database)
