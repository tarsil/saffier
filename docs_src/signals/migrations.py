from saffier.core.signals import post_migrate, pre_migrate


@pre_migrate.connect_via("upgrade")
def announce_upgrade(sender, revision, sql, **kwargs):
    """Run just before an upgrade command reaches Alembic.

    Args:
        sender: Migration command name. For this receiver it is always
            ``"upgrade"``.
        revision: Target Alembic revision.
        sql: Whether the command is producing SQL output instead of applying
            migrations.
        **kwargs: Additional command metadata, including the Alembic config.
    """
    print(f"Starting {sender} to {revision}; sql={sql}")


@post_migrate.connect_via("upgrade")
async def seed_after_upgrade(sender, _async_wrapper, **kwargs):
    """Run after an upgrade command completes successfully.

    Args:
        sender: Migration command name. For this receiver it is always
            ``"upgrade"``.
        _async_wrapper: Synchronous bridge exposed to migration receivers.
        **kwargs: Additional command metadata, including the Alembic config.
    """
    print(f"Finished {sender}")
