CASCADE = "CASCADE"
RESTRICT = "RESTRICT"
DO_NOTHING = "DO NOTHING"
SET_NULL = "SET NULL"
SET_DEFAULT = "SET DEFAULT"
PROTECT = "PROTECT"


class NEW_M2M_NAMING:
    """
    Marker for the field-oriented through-table naming convention.
    """


class ConditionalRedirect(dict):
    """
    Lightweight pure-Python equivalent used by composite-field integrations.
    """


__all__ = [
    "CASCADE",
    "RESTRICT",
    "DO_NOTHING",
    "SET_NULL",
    "SET_DEFAULT",
    "PROTECT",
    "NEW_M2M_NAMING",
    "ConditionalRedirect",
]
