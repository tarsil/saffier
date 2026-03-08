# `ForeignKey`

`ForeignKey` stores a relation to another Saffier model.

## What it supports

Saffier foreign keys support more than a simple single-column integer target:

* direct model classes or deferred string targets
* nested unsaved model instances during `save()`
* reverse-relation generation through `related_name`
* composite target keys through multiple generated columns
* `no_constraint=True` for cross-registry or cross-database relationships

## Practical declaration

```python
class Profile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    user = saffier.ForeignKey(
        "User",
        on_delete=saffier.CASCADE,
        related_name="profiles",
    )

    class Meta:
        registry = models
```

## Runtime behavior to keep in mind

Passing `user=<User instance>` is valid. If the related object has not been
saved yet, Saffier saves it first and then persists the foreign-key columns on
the parent model.

Reverse accessors are installed on the target model when the registry resolves
the relation.

::: saffier.ForeignKey
    options:
        filters:
        - "!^_type"
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
