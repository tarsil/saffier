import saffier

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database, model_engine="pydantic")


class Product(saffier.Model):
    sku = saffier.CharField(max_length=50)
    price = saffier.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        registry = models


class AuditLog(saffier.Model):
    event = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        model_engine = False


class LegacyProfile(saffier.Model):
    display_name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        model_engine = "pydantic"
