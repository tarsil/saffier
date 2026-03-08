import saffier

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database)


class Event(saffier.Model):
    name = saffier.CharField(max_length=100)
    retries = saffier.IntegerField(default=0)
    topic = saffier.CharField(max_length=100, null=True)

    class Meta:
        registry = models
        model_engine = "msgspec"


payload = Event.engine_validate({"name": "job", "retries": "2", "topic": None})
event = Event.from_engine({"name": "job", "retries": "2", "topic": None})
engine_event = event.to_engine_model()
dumped = event.engine_dump()
schema = Event.engine_json_schema(mode="validation")
