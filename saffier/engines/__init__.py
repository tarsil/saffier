"""Optional engine adapters for Saffier models."""

from saffier.engines.base import (
    EngineIncludeExclude,
    ModelEngine,
    ModelEngineRegistry,
    get_model_engine,
    register_model_engine,
    resolve_model_engine,
)
from saffier.engines.msgspec import MsgspecModelEngine
from saffier.engines.pydantic import PydanticModelEngine

register_model_engine("pydantic", PydanticModelEngine, overwrite=True)
register_model_engine("msgspec", MsgspecModelEngine, overwrite=True)

__all__ = [
    "EngineIncludeExclude",
    "ModelEngine",
    "ModelEngineRegistry",
    "MsgspecModelEngine",
    "PydanticModelEngine",
    "get_model_engine",
    "register_model_engine",
    "resolve_model_engine",
]
