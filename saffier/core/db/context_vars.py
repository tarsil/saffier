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


def get_schema() -> str | None:
    return SHEMA.get()


def set_schema(value: str | None) -> None:
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
