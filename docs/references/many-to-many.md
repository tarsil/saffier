# `ManyToManyField`

`ManyToManyField` is a virtual field backed by a through model.

It does not create columns on the owning model. Instead it either uses an
explicit through model or generates one automatically and exposes a runtime
relation descriptor for collection-style access.

## Practical example

```python
class Article(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    tags = saffier.ManyToManyField("Tag")

    class Meta:
        registry = models
```

## Important behaviors

* the through model must expose an integer `id` primary key
* `add()`, `add_many()`, `create()`, `remove()`, and `remove_many()` operate
  through the junction model
* `embed_through` can attach the through instance back onto the related object
  after relation operations
* reverse names are generated from the owning model and field name when you do
  not declare one explicitly

::: saffier.ManyToManyField
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
        - "!^_type"
