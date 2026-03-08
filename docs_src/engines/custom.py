import saffier


class DictEngine(saffier.ModelEngine):
    name = "dict"

    def get_model_class(self, model_class, *, mode="projection"):
        del model_class, mode
        return dict

    def validate_model(self, model_class, value, *, mode="validation"):
        del model_class, mode
        if hasattr(value, "__db_model__"):
            return self.build_projection_payload(value)
        return dict(value)

    def to_saffier_data(self, model_class, value, *, exclude_unset=False):
        del model_class, exclude_unset
        return dict(value)

    def json_schema(self, model_class, *, mode="projection", **kwargs):
        del kwargs
        return {
            "title": f"{model_class.__name__}{mode.title()}DictEngine",
            "type": "object",
        }


saffier.register_model_engine("dict", DictEngine())

database = saffier.Database("postgresql+asyncpg://postgres:postgres@localhost:5432/app")
models = saffier.Registry(database=database, model_engine="dict")


class AuditEntry(saffier.Model):
    event = saffier.CharField(max_length=100)

    class Meta:
        registry = models
