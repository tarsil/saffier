from myapp.models import HubUser, Product, Tenant, TenantUser, User

from saffier import Database

database = Database("<YOUR-CONNECTION-STRING>")


async def create_data():
    """
    Creates mock data
    """
    # Global users
    john = await User.query.create(name="John Doe", email="john.doe@esmerald.dev")
    saffier = await User.query.create(name="Saffier", email="saffier@esmerald.dev")

    # Tenant
    tenant = await Tenant.query.create(schema_name="saffier", tenant_name="saffier")

    # HubUser - A user specific inside the saffier schema
    tenant_schema_user = await HubUser.query.using(tenant.schema_name).create(
        name="saffier", email="saffier@esmerald.dev"
    )

    await TenantUser.query.create(user=saffier, tenant=tenant)

    # Products for Saffier HubUser specific
    for i in range(10):
        await Product.query.using(tenant.schema_name).create(
            name=f"Product-{i}", user=tenant_schema_user
        )

    # Products for the John without a tenant associated
    for i in range(25):
        await Product.query.create(name=f"Product-{i}", user=john)


# Start the db
await database.connect()

# Run the create_data
await create_data()

# Close the database connection
await database.disconnect()
