import saffier
from lilya.apps import Lilya


database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database)

app = models.asgi(Lilya())
