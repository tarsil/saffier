import saffier

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database, model_engine="pydantic")


class User(saffier.Model):
    email = saffier.EmailField(max_length=255)
    name = saffier.CharField(max_length=120)

    class Meta:
        registry = models


user = User(name="Ada", email="ada@example.com")
engine_user = user.to_engine_model()
validated = User.engine_validate({"name": "Ada", "email": "ada@example.com"})
rebuilt = User.from_engine(validated)
