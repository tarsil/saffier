from contextvars import ContextVar
from typing import Any

model_factory_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "saffier_model_factory_context",
    default=None,
)
