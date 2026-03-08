# Permissions

Saffier includes a Python-native permission contrib built around an abstract `BasePermission`
model and a dedicated `PermissionManager`.

## Base Permission Model

```python
import saffier
from saffier.contrib.permissions import BasePermission


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Group(saffier.Model):
    name = saffier.CharField(max_length=100)
    users = saffier.ManyToMany("User")

    class Meta:
        registry = models


class Permission(BasePermission):
    users = saffier.ManyToMany("User")
    groups = saffier.ManyToMany("Group")

    class Meta:
        registry = models
```

`BasePermission` provides:

* `name`: permission name.
* `description`: computed field with overridable getter/setter.
* `query`: `PermissionManager`.

## Manager Helpers

The manager exposes helpers for common ACL queries:

* `permissions_of(source_or_sources)`: permissions assigned to users/groups.
* `users(permissions, model_names=None, objects=None)`: users with effective permissions.
* `groups(permissions, model_names=None, objects=None)`: groups with permissions.

These methods return querysets, so you can keep chaining filters/orderings.
