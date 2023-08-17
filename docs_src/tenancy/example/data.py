async def create_data():
    """
    Creates mock data.
    """
    # Create some users in the main users table
    esmerald = await User.query.create(name="esmerald")

    # Create a tenant for Saffier (only)
    tenant = await Tenant.query.create(
        schema_name="saffier",
        tenant_name="saffier",
    )

    # Create a user in the `User` table inside the `saffier` tenant.
    saffier = await User.query.using(tenant.schema_name).create(
        name="Saffier schema user",
    )

    # Products for Saffier (inside saffier schema)
    for i in range(10):
        await Product.query.using(tenant.schema_name).create(
            name=f"Product-{i}",
            user=saffier,
        )

    # Products for Esmerald (no schema associated, defaulting to the public schema or "shared")
    for i in range(25):
        await Product.query.create(name=f"Product-{i}", user=esmerald)
