# `OneToOneField`

`OneToOneField` is the unique variant of `ForeignKey`.

It behaves like a foreign key at declaration and query time, but the generated
relation columns are unique and the reverse accessor is singular by default.

## Practical example

```python
class Profile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    user = saffier.OneToOneField("User", on_delete=saffier.CASCADE)

    class Meta:
        registry = models
```

## Reverse behavior

When `related_name` is omitted, Saffier generates a singular reverse accessor
from the declaring model name. That means a `Profile.user` relation typically
becomes `user.profile`, not `user.profiles_set`.

For reverse one-to-one relations, `remove()` can omit the child object because
at most one related row can exist.

::: saffier.OneToOneField
    options:
        filters:
        - "!^_type"
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
        - "!^__new__"
