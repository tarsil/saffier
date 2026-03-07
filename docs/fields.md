# Fields

Fields are what is used within model declaration (data types) and defines wich types are going to
be generated in the SQL database when generated.

## Data types

As **Saffier** is a new approach on the top of Encode ORM, the following keyword arguments are
supported in **all field types**.

!!! Check
    The data types are also very familiar for those with experience with Django model fields.

* **primary_key** - A boolean. Determine if a column is primary key.
Check the [primary_key](./models.md#restrictions-with-primary-keys) restrictions with Saffier.
* **null** - A boolean. Determine if a column allows null.
* **default** - A value or a callable (function).
* **index** - A boolean. Determine if a database index should be created.
* **unique** - A boolean. Determine if a unique constraint should be created for the field.
Check the [unique_together](./models.md#unique-together) for more details.

All the fields are required unless on the the following is set:

* **null** - A boolean. Determine if a column allows null.

    <sup>Set default to `None`</sup>

* **blank** - A boolean. Determine if empry strings are allowed. This can be useful if you want to
build an admin-like application.

    <sup>Set default to `""`</sup>

* **default** - A value or a callable (function).
* **server_default** - nstance, str, Unicode or a SQLAlchemy `sqlalchemy.sql.expression.text`
construct representing the DDL DEFAULT value for the column.
* **comment** - A comment to be added with the field in the SQL database.

## Available fields

Saffier follows a Python-native field and validation layer inspired by `typesystem`. This means,
for example, that migrating from Encode ORM is almost direct because core patterns, names,
and validation semantics remain intentionally familiar.

To make the interface even more familiar, the field names end with a `Field` at the end.

### Importing fields

You have a few ways of doing this and those are the following:

```python
import saffier
```

From `saffier` you can access all the available fields.

```python
from saffier.core.db import fields
```

From `fields` you should be able to access the fields directly.

```python
from saffier.core.db.fields import BigIntegerField
```

You can import directly the desired field.

All the fields have specific parameters beisdes the ones [mentioned in data types](#data-types).

Saffier also exposes dedicated field modules for import ergonomics:

```python
from saffier.core.db.fields.composite_field import CompositeField
from saffier.core.db.fields.foreign_keys import ForeignKey, RefForeignKey
from saffier.core.db.fields.many_to_many import ManyToManyField
from saffier.core.db.fields.one_to_one_keys import OneToOneField
```

#### BigIntegerField

```python
import saffier


class MyModel(saffier.Model):
    big_number = saffier.BigIntegerField(default=0)
    another_big_number = saffier.BigIntegerField(minimum=10)
    ...

```

This field is used as a default field for the `id` of a model.

##### Parameters:

* **minimum** - An integer, float or decimal indicating the minimum.
* **maximum** - An integer, float or decimal indicating the maximum.
* **exclusive_minimum** - An integer, float or decimal indicating the exclusive minimum.
* **exclusive_maximum** - An integer, float or decimal indicating the exclusive maximum.
* **precision** - A string indicating the precision.
* **multiple_of** - An integer, float or decimal indicating the multiple of.

#### IntegerField

```python
import saffier


class MyModel(saffier.Model):
    a_number = saffier.IntegerField(default=0)
    another_number = saffier.IntegerField(minimum=10)
    ...

```

##### Parameters:

* **minimum** - An integer, float or decimal indicating the minimum.
* **maximum** - An integer, float or decimal indicating the maximum.
* **exclusive_minimum** - An integer, float or decimal indicating the exclusive minimum.
* **exclusive_maximum** - An integer, float or decimal indicating the exclusive maximum.
* **precision** - A string indicating the precision.
* **multiple_of** - An integer, float or decimal indicating the multiple of.

#### BooleanField

```python
import saffier


class MyModel(saffier.Model):
    is_active = saffier.BooleanField(default=True)
    is_completed = saffier.BooleanField(default=False)
    ...

```

#### CharField

```python
import saffier


class MyModel(saffier.Model):
    description = saffier.CharField(max_length=255)
    title = saffier.CharField(max_length=50, minimum_length=200)
    ...

```

##### Parameters:

* **max_length** - An integer indicating the total length of string.
* **min_length** - An integer indicating the minimum length of string.

#### ChoiceField

```python
from enum import Enum
import saffier

class Status(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class MyModel(saffier.Model):
    status = saffier.ChoiceField(choices=Status, default=Status.ACTIVE)
    ...

```

##### Parameters

* **choices** - An enum containing the choices for the field.

#### CharChoiceField

A character-backed choice field. Useful when you want enum-like semantics but explicit string
storage.

```python
from enum import Enum
import saffier


class Status(Enum):
    PENDING = "pending"
    DONE = "done"


class Job(saffier.Model):
    status = saffier.CharChoiceField(choices=Status, max_length=20)
```

#### DateField

```python
import datetime
import saffier


class MyModel(saffier.Model):
    created_at = saffier.DateField(default=datetime.date.today)
    ...

```

##### Parameters

* **auto_now** - A boolean indicating the `auto_now` enabled. Useful for auto updates.
* **auto_now_add** - A boolean indicating the `auto_now_add` enabled. This will ensure that it is
only added once.

#### DateTimeField

```python
import datetime
import saffier


class MyModel(saffier.Model):
    created_at = saffier.DateTimeField(datetime.datetime.now)
    ...

```

##### Parameters

* **auto_now** - A boolean indicating the `auto_now` enabled. Useful for auto updates.
* **auto_now_add** - A boolean indicating the `auto_now_add` enabled. This will ensure that it is
only added once.

#### DecimalField

```python
import saffier


class MyModel(saffier.Model):
    price = saffier.DecimalField(max_digits=5, decimal_places=2, null=True)
    ...

```

##### Parameters

* **max_digits** - An integer indicating the total maximum digits.
* **decimal_places** - An integer indicating the total decimal places.

#### EmailField

```python
import saffier


class MyModel(saffier.Model):
    email = saffier.EmailField(max_length=60, null=True)
    ...

```

Derives from the same as [CharField](#charfield) and validates the email value.

#### FloatField

```python
import saffier


class MyModel(saffier.Model):
    email = saffier.FloatField(null=True)
    ...

```

Derives from the same as [IntergerField](#integerfield) and validates the decimal float.

#### SmallIntegerField

```python
import saffier


class Counter(saffier.Model):
    tiny_value = saffier.SmallIntegerField(default=0)
```

#### DurationField

Stores `datetime.timedelta` using SQL `INTERVAL`.

```python
import datetime
import saffier


class Timer(saffier.Model):
    elapsed = saffier.DurationField(default=datetime.timedelta)
```

#### BinaryField

Stores bytes payloads using SQL `LargeBinary`.

```python
import saffier


class Attachment(saffier.Model):
    blob = saffier.BinaryField(max_length=4096, null=True)
```

#### ExcludeField

Virtual field used to reserve an attribute name without creating a database column.

```python
import saffier


class MyModel(saffier.Model):
    transient = saffier.ExcludeField()
```

#### PlaceholderField

Alias of `ExcludeField` used for placeholder semantics.

```python
import saffier


class MyModel(saffier.Model):
    placeholder = saffier.PlaceholderField()
```

#### ComputedField

Virtual field whose value is resolved by getter/setter callbacks.

Computed fields are excluded from `model_dump()` by default, matching Edgy's
runtime serialization behavior. Set `exclude=False` when the computed value
should be part of serialized model output.

```python
import saffier


class Permission(saffier.Model):
    name = saffier.CharField(max_length=100)
    description = saffier.ComputedField(
        getter="get_description",
        setter="set_description",
        exclude=False,
    )

    class Meta:
        abstract = True

    @classmethod
    def get_description(cls, field, instance, owner=None):
        return instance.name.upper()
```

#### CompositeField

Virtual grouping field that exposes multiple underlying fields as one structured attribute.

```python
import saffier


class Customer(saffier.Model):
    first_name = saffier.CharField(max_length=120)
    last_name = saffier.CharField(max_length=120)

    # Reads/writes both fields as one dictionary.
    full_name = saffier.CompositeField(inner_fields=["first_name", "last_name"])

    # Declares embedded real columns.
    contact = saffier.CompositeField(
        inner_fields=[
            ("email", saffier.EmailField(max_length=255, null=True)),
            ("phone", saffier.CharField(max_length=64, null=True)),
        ],
        prefix_embedded="contact_",
    )
```

`CompositeField` itself is virtual and does not create a database column. Embedded inner fields do.

Saffier also accepts an abstract model class on the model body and converts it into a prefixed
`CompositeField` automatically, matching Edgy's embedded-model shorthand.

```python
class Address(saffier.Model):
    street = saffier.CharField(max_length=100)
    city = saffier.CharField(max_length=100)

    class Meta:
        abstract = True


class ProfileHolder(saffier.Model):
    address = Address
```

The generated columns are `address_street` and `address_city`, while `holder.address` reads and
writes the embedded object as a single value.

#### FileField

String-backed field for file references/paths.

```python
import saffier


class Asset(saffier.Model):
    file_ref = saffier.FileField(null=True)
```

#### ImageField

String-backed field for image references/paths.

```python
import saffier


class Asset(saffier.Model):
    image_ref = saffier.ImageField(null=True)
```

#### PGArrayField

PostgreSQL `ARRAY` field with mutable list tracking.

```python
import sqlalchemy
import saffier


class User(saffier.Model):
    tags = saffier.PGArrayField(sqlalchemy.String(), null=True)
```

#### ForeignKey

```python
import saffier


class User(saffier.Model):
    is_active = saffier.BooleanField(default=True)


class Profile(saffier.Model):
    is_enabled = saffier.BooleanField(default=True)


class MyModel(saffier.Model):
    user = saffier.ForeignKey("User", on_delete=saffier.CASCADE)
    profile = saffier.ForeignKey(Profile, on_delete=saffier.CASCADE, related_name="my_models")
    ...

```

##### Parameters

* **to** - A string [model](./models.md) name or a class object of that same model.
* **related_name** - The name to use for the relation from the related object back to this one.
  Set it to `False` to disable the reverse relation entirely.
  When omitted on `OneToOneField`, Saffier generates the singular reverse accessor instead of the
  plural `*_set` name.
* **on_delete** - A string indicating the behaviour that should happen on delete of a specific
model. The available values are `CASCADE`, `SET_NULL`, `RESTRICT` and those can also be imported
from `saffier`.
* **on_update** - A string indicating the behaviour that should happen on update of a specific
model. The available values are `CASCADE`, `SET_NULL`, `RESTRICT` and those can also be imported
from `saffier`.
* **no_constraint** - Disable the database-level foreign key constraint while still keeping the
  Saffier relation. This is useful for shared registries, cross-database links, and tenant models
  that point at shared content type rows.

    ```python
    from saffier import CASCADE, SET_NULL, RESTRICT
    ```

#### RefForeignKey

`RefForeignKey` supports two modes in Saffier.

If you pass a real Saffier model, it behaves like a regular `ForeignKey` and keeps the extra
`ref_field` metadata for tooling or custom conventions.

```python
import saffier


class Team(saffier.Model):
    slug = saffier.CharField(max_length=120, unique=True)


class Member(saffier.Model):
    team = saffier.RefForeignKey(Team, ref_field="slug", on_delete=saffier.CASCADE)
```

If you pass a `ModelRef` subclass instead, `RefForeignKey` becomes a virtual nested-insert field.
This is the Saffier-native pure Python adaptation of Edgy's reference workflow.

```python
class PostRef(saffier.ModelRef):
    __related_name__ = "posts_set"
    comment: str


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100, null=True)
    posts = saffier.RefForeignKey(PostRef, null=True)
```

```python
await User.query.create(
    PostRef(comment="created from a positional ModelRef"),
    name="Alice",
    posts=[],
)
```

See [Reference ForeignKey](./reference-foreignkey.md) for the full workflow.

#### ManyToMany

```python
import saffier


class User(saffier.Model):
    is_active = saffier.BooleanField(default=True)


class Organisation(saffier.Model):
    is_enabled = saffier.BooleanField(default=True)


class MyModel(saffier.Model):
    users = saffier.ManyToMany(User)
    organisations = saffier.ManyToMany("Organisation")

```

!!! Tip
    You can use `saffier.ManyToManyField` as alternative to `ManyToMany` instead.

##### Parameters

* **to** - A string [model](./models.md) name or a class object of that same model.
* **related_name** - The name to use for the relation from the related object back to this one.
* **through** - The model to be used for the relationship. Saffier generates the model by default
if none is provided.
* **through_tablename** - Controls the table name used for the auto-generated through model.
  Saffier uses the field-based naming scheme by default, which is the same
  behavior as `saffier.NEW_M2M_NAMING`. You can still pass
  `saffier.NEW_M2M_NAMING` explicitly or provide a non-empty string.
  String values support `str.format(field=...)`.
* **embed_through** - When set to a string, queryset results return the related model and attach
  the intermediate through row on that attribute. This also enables query paths such as
  `organisation.teams.filter(membership__team__name="Blue Team")` when
  `embed_through="membership"`.
* **unique** - Marks the target side of the generated through model as unique, producing a
  reverse relation that behaves like Edgy's unique many-to-many variant.

!!! Note
    Saffier enforces an auto-incrementing integer `id` primary key on ManyToMany through models.
    Auto-generated through models always include it, and custom through models must also expose
    `id` as the primary key.

!!! Warning
    Saffier intentionally does not support Edgy's legacy `OLD_M2M_NAMING`
    marker. Auto-generated through models always use the field-based naming
    path unless you provide an explicit table name yourself.

!!! Tip
    String values for `through_tablename` are formatted with `field=self` before
    being lowercased. This lets you derive stable names from the owner model and
    field name when you need custom naming.

#### IPAddressField

```python
import saffier


class MyModel(saffier.Model):
    ip_address = saffier.IPAddressField()
    ...

```

Derives from the same as [CharField](#charfield) and validates the value of an IP. It currently
supports `ipv4` and `ipv6`.

#### JSONField

```python
import saffier


class MyModel(saffier.Model):
    data = saffier.JSONField(default={})
    ...

```

Simple JSON representation object.

#### OneToOne

```python
import saffier


class User(saffier.Model):
    is_active = saffier.BooleanField(default=True)


class MyModel(saffier.Model):
    user = saffier.OneToOne("User")
    ...

```

Derives from the same as [ForeignKey](#foreignkey) and applies a One to One direction.

!!! Tip
    You can use `saffier.OneToOneField` as alternative to `OneToOne` instead.

#### TextField

```python
import saffier


class MyModel(saffier.Model):
    data = saffier.TextField(null=True, blank=True)
    ...

```

Similar to [CharField](#charfield) but has no `max_length` restrictions.

#### PasswordField

```python
import saffier


class MyModel(saffier.Model):
    data = saffier.PasswordField(null=False, max_length=255)
    ...

```

Similar to [CharField](#charfield) and it can be used to represent a password text.

#### TimeField

```python
import datetime
import saffier


def get_time():
    return datetime.datetime.now().time()


class MyModel(saffier.Model):
    time = saffier.TimeField(default=get_time)
    ...

```

##### Parameters

* **auto_now** - A boolean indicating the `auto_now` enabled.
* **auto_now_add** - A boolean indicating the `auto_now_add` enabled.

#### URLField

```python
import saffier


class MyModel(saffier.Model):
    url = fields.URLField(null=True, max_length=1024)
    ...

```

Derives from the same as [CharField](#charfield) and validates the value of an URL.

#### UUIDField

```python
import saffier


class MyModel(saffier.Model):
    uuid = fields.UUIDField()
    ...

```

Derives from the same as [CharField](#charfield) and validates the value of an UUID.
