# Relationships

Relationships are where Saffier stops looking like a collection of individual
models and starts behaving like an ORM.

At declaration time, relation fields describe how models point to each other.
At runtime, those same fields install reverse descriptors, normalize nested
objects during save operations, and control how eager loading works in
querysets.

This page focuses on the three important mental models:

* declaration: how to describe the relation
* runtime access: what you get back on model instances
* persistence: what happens when related objects are unsaved, nullable, or
  reverse-managed

There are currently two direct relation field types documented here:
[ForeignKey](./fields.md#foreignkey) and
[OneToOneField](./fields.md#onetoonefield).

When declaring a relation, you can target another model either by passing the
model class directly or by using a string name that the registry resolves
later.

!!! Tip
    Have a look at the [related name](./queries/related-name.md) documentation to understand how
    you can leverage reverse queries with foreign keys.

## ForeignKey

Let us define the following models `User` and `Profile`.

```python
{!> ../docs_src/relationships/model.py !}
```

Now let us create some entries for those models.

```python
user = await User.query.create(first_name="Foo", email="foo@bar.com")
await Profile.query.create(user=user)

user = await User.query.create(first_name="Bar", email="bar@foo.com")
await Profile.query.create(user=user)
```

### Multiple foreign keys pointing to the same table

What if you want to have multiple foreign keys pointing to the same model? This is also easily
possible to achieve.

```python
{!> ../docs_src/relationships/multiple.py !}
```

In real applications this pattern shows up in audit tables, approval flows, and
messaging systems where one model can play several roles in the same row:

* `created_by`
* `updated_by`
* `approved_by`
* `owner`

!!! Tip
    Have a look at the [related name](./queries/related-name.md) documentation to understand how
    you can leverage reverse queries with foreign keys withe the
    [related_name](./queries/related-name.md#related_name-attribute).

### Reverse relation mutation helpers

Reverse foreign-key relations expose the same mutation helpers as Edgy's current runtime:
`add()`, `add_many()`, `create()`, `remove()`, and `remove_many()`.

```python
album = await Album.query.create(name="Malibu")
track = await Track.query.create(title="The Bird", position=1)

await album.tracks_set.add(track)
await album.tracks_set.create(title="Heart don't stand a chance", position=2)
await album.tracks_set.remove(track)
```

You can also stage reverse children during parent creation or save:

```python
track1 = await Track.query.create(title="The Bird", position=1)
track2 = await Track.query.create(title="Heart don't stand a chance", position=2)

album = await Album.query.create(name="Malibu", tracks_set=[track1, track2])
```

### Load an instance without the foreign key relationship on it

```python
profile = await Profile.query.get(id=1)

# We have an album instance, but it only has the primary key populated
print(profile.user)       # User(id=1) [sparse]
print(profile.user.pk)    # 1
print(profile.user.email)  # Raises AttributeError
```

### Load an instance with the foreign key relationship on it

```python
profile = await Profile.query.get(user__id=1)

await profile.user.load() # loads the foreign key
```

### Load an instance with the foreign key relationship on it with select related

```python
profile = await Profile.query.select_related("user").get(id=1)

print(profile.user)       # User(id=1) [sparse]
print(profile.user.pk)    # 1
print(profile.user.email)  # foo@bar.com
```

### Access the foreign key values directly from the model

!!! Note
    This is only possible since the version 1.3.0 of **Saffier**, before this version, the only way was
    by using the [select_related](#load-an-instance-with-the-foreign-key-relationship-on-it-with-select-related) or
    using the [load()](./queries/queries.md#load-the-foreign-keys-beforehand-with-select-related).

You can access the values of the foreign keys of your model directly via model instance without
using the [select_related](#load-an-instance-with-the-foreign-key-relationship-on-it-with-select-related) or
the [load()](./queries/queries.md#load-the-foreign-keys-beforehand-with-select-related).

Let us see an example.

**Create a user and a profile**

```python
user = await User.query.create(first_name="Foo", email="foo@bar.com")
await Profile.query.create(user=user)
```

**Accessing the user data from the profile**

```python
profile = await Profile.query.get(user__email="foo@bar.com")

print(profile.user.email) # "foo@bar.com"
print(profile.user.first_name) # "Foo"
```

## ForeignKey constraints

As mentioned in the [foreign key field](./fields.md#foreignkey), you can specify constraints in
a foreign key.

The available values are `CASCADE`, `SET_NULL`, `RESTRICT` and those can also be imported
from `saffier`.

```python
from saffier import CASCADE, SET_NULL, RESTRICT
```

When declaring a foreign key or a one to one key, the **on_delete must be provided** or an
`AssertationError` is raised.

Looking back to the previous example.

```python
{!> ../docs_src/relationships/model.py !}
```

`Profile` model defines a `saffier.ForeignKey` to the `User` with `on_delete=saffier.CASCADE` which
means that whenever a `User` is deleted from the database, all associated `Profile` instances will
also be removed.

### Delete options

* **CASCADE** - Remove all referencing objects.
* **RESTRICT** - Restricts the removing referenced objects.
* **SET_NULL** - This will make sure that when an object is deleted, the associated referencing
instances pointing to that object will set to null. When this `SET_NULL` is true, the `null=True`
must be also provided or an `AssertationError` is raised.

If you need to keep the Python-side relation without a database-level foreign key constraint, pass
`no_constraint=True`. Saffier uses this for shared content type registries and tenant content type
links where the target row lives outside the current table metadata.

## OneToOneField

Creating an `OneToOneField` relationship between models is basically the same as the
[ForeignKey](#foreignkey) with the key difference that it uses `unique=True` on the foreign key
column.

```python
{!> ../docs_src/relationships/onetoone.py !}
```

The same rules for this field are the same as the [ForeignKey](#foreignkey) as this derives from it.

Let us create a `User` and a `Profile`.

```python
user = await User.query.create(email="foo@bar.com")
await Profile.query.create(user=user)
```

### Reverse one-to-one names

When `related_name` is omitted on a one-to-one field, Saffier now follows Edgy's current behavior
and generates the singular reverse name from the declaring model.

```python
class Profile(saffier.Model):
    ...


class Person(saffier.Model):
    profile = saffier.OneToOneField(Profile, on_delete=saffier.CASCADE, null=True)
```

The reverse accessor on `Profile` is `profile.person`, not `profile.persons_set`.

Because reverse one-to-one relations are unique, `remove()` can omit the child:

```python
await profile.person.remove()
```

Now creating another `Profile` with the same user will fail and raise an exception.

```
await Profile.query.create(user=user)
```
