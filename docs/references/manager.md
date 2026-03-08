# `Manager`

Managers are the descriptor layer between model classes and querysets.

The default `query` manager is how most code enters the ORM, but custom
managers are also the standard way to package reusable queryset defaults or
project-specific query helpers.

## Descriptor behavior

Managers are class-aware and instance-aware:

* on a model class, the manager is bound to the class
* on a model instance, the manager is shallow-copied and bound to that instance

That instance binding is what allows schema-aware or database-aware managers to
follow an instance context without mutating the class-level manager.

## Typical customization

```python
class ActiveUsers(saffier.Manager):
    def get_queryset(self) -> saffier.QuerySet:
        return super().get_queryset().filter(is_active=True)


class User(saffier.Model):
    query: ClassVar[saffier.Manager] = saffier.Manager()
    active: ClassVar[ActiveUsers] = ActiveUsers()
```

::: saffier.Manager
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
