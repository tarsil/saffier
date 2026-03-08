CASCADE = "CASCADE"
RESTRICT = "RESTRICT"
DO_NOTHING = "DO NOTHING"
SET_NULL = "SET NULL"
SET_DEFAULT = "SET DEFAULT"
PROTECT = "PROTECT"


class NEW_M2M_NAMING:
    """Marker selecting the newer field-oriented many-to-many naming scheme."""


class ConditionalRedirect(dict):
    """Dictionary marker used by composite-field redirect integrations."""


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
