# **`OneToOne`** class

`OneToOneField` supports `embed_parent=("path", "attr")` for reverse relation querysets.
When a reverse queryset is loaded through that relation, Saffier returns the embedded parent
object at `path` and attaches the intermediate model on `attr`.

```python
class Profile(saffier.Model):
    user = saffier.OneToOneField(User, related_name="profile")
    profile = saffier.OneToOneField(
        "SuperProfile",
        related_name="profile",
        embed_parent=("user", "normal_profile"),
    )
```


::: saffier.OneToOneField
    options:
        filters:
        - "!^_type"
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
        - "!^__new__"
