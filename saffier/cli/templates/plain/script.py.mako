"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade(engine_name: str = "") -> None:
    fn = globals().get(f"upgrade_{engine_name}")
    if fn is not None:
        fn()


def downgrade(engine_name: str = "") -> None:
    fn = globals().get(f"downgrade_{engine_name}")
    if fn is not None:
        fn()
<%
    import saffier
    db_names = saffier.monkay.settings.migrate_databases
%>

## generate an "upgrade_<xyz>() / downgrade_<xyz>()" function
## according to saffier migrate settings

% for db_name in db_names:

def ${f"upgrade_{db_name or ''}"}(db_name: str = ""):
    ${context.get(f"{db_name or ''}_upgrades", "pass")}


def ${f"downgrade_{db_name or ''}"}():
    ${context.get(f"{db_name or ''}_downgrades", "pass")}

% endfor
