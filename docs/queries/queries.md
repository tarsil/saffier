# Queries

Making queries is a must when using an ORM and being able to make complex queries is even better
when allowed.

SQLAlchemy is known for its performance when querying a database and it is very fast. The core
being part of **Saffier** also means that saffier performs extremely well when doing it.

When making queries in a [model][model], the ORM uses the [managers][managers] to
perform those same actions.

If you haven't yet seen the [models][model] and [managers][managers] section, now would
be a great time to have a look and get yourself acquainted.

## QuerySet

When making queries within Saffier, this return or an object if you want only one result or a
`queryset` which is the internal representation of the results.

If you are familiar with Django querysets, this is **almost** the same and by almost is because
saffier restricts loosely queryset variable assignments.

Let us get familar with queries.

Let us assume you have the following `User` model defined.

```python
{!> ../docs_src/queries/model.py !}
```

As mentioned before, Saffier returns queysets and simple objects and when queysets are returned
those can be chained together, for example, with `filter()` or `limit()`.

```python
await User.query.filter(is_active=True).filter(first_name__icontains="a").order_by("id")
```

Do we really need two filters here instead of one containing both conditions? No, we do not but
this is for example purposes.

Internally when querying the model and with returning querysets, **Saffier** runs the `all()`.
This can be done manually by you or automatically by the ORM.

Let us refactor the previous queryset and apply the manual `all()`.

```python
await User.query.filter(is_active=True, first_name__icontains="a").order_by("id").all()
```

And that is it. Of course there are more filters and operations that you can do with the ORM and
we will be covering that in this document but in a nutshell, querying the database is this simple.

## Load the foreign keys beforehand with select related

Select related is a functionality that *follows the foreign-key relationships* by selecting any
additional related object when a query is executed. You can imagine it as a classic `join`.

The difference is that when you execute the [select_related](../relationships.md#load-an-instance-with-the-foreign-key-relationship-on-it-with-select-related),
the foreign keys of the model being used by that operation will be opulated with the database results.

You can use the classic [select_related](../relationships.md#load-an-instance-with-the-foreign-key-relationship-on-it-with-select-related):

```python
await Profile.query.select_related("user").get(id=1)
```

Or you can use the `load()` function of the model for the foreign key. Let us refactor the example above.

```python
profile = await Profile.query.get(id=1)
await profile.user.load()
```

The `load()` works on any foreign key declared and it will automatically load the data into that
field.

## Returning querysets

There are many operations you can do with the querysets and then you can also leverage those for
your use cases.

### Exclude

The `exclude()` is used when you want to filter results by excluding instances.

```python
users = await User.query.exclude(is_active=False)
```

### Filter

#### Django-style

These filters are the same **Django-style** lookups.

```python
users = await User.query.filter(is_active=True, email__icontains="gmail")
```

The same special operators are also automatically added on every column.

* **in** - SQL `IN` operator.
* **exact** - Filter instances matching the exact value.
* **iexact** - Filter instances mathing the exact value but case-insensitive.
* **contains** - Filter instances that contains a specific value.
* **icontains** - Filter instances that contains a specific value but case-insensitive.
* **lt** - Filter instances having values `Less Than`.
* **lte** - Filter instances having values `Less Than Equal`.
* **gt** - Filter instances having values `Greater Than`.
* **gte** - Filter instances having values `Greater Than Equal`.
* **isempty** - Filter instances where a field holds its Edgy-style empty value.
* **isnull** - Filter instances where a column is `NULL` or not `NULL`.

##### Example

```python
users = await User.query.filter(email__icontains="foo")

users = await User.query.filter(id__in=[1, 2, 3])

users = await User.query.filter(name__isempty=True)

users = await User.query.filter(last_login__isnull=True)
```

#### SQLAlchemy style

Since Saffier uses SQLAlchemy core, it is also possible to do queries in SQLAlchemy style.
The filter accepts also those.

If you need direct class-attribute access such as `User.id` instead of
`User.columns.id`, see [SQLAlchemy compatibility mode](./sqlalchemy-compatibility.md).

##### Example

```python
users = await User.query.filter(User.columns.email.contains("foo"))

users = await User.query.filter(User.columns.id.in_([1, 2, 3]))
```

#### Q expressions

For nested boolean predicates, use [`Q`](q.md).

```python
from saffier import Q

users = await User.query.filter((Q(name="Adam") & Q(email__icontains="saffier")) | ~Q(id=1))
```

### Local OR

Use `local_or()` to combine OR clauses with existing queryset filters:

```python
users = await User.query.filter(is_active=True).local_or(email__icontains="example.com")
```

!!! Warning
    The `columns` refers to the columns of the underlying SQLAlchemy table.

### Limit

Limiting the number of results. The `LIMIT` in SQL.

```python
users = await User.query.limit(1)

users = await User.query.filter(email__icontains="foo").limit(2)
```

### Offset

Applies the office to the query results.

```python
users = await User.query.offset(1)

users = await User.query.filter(is_active=False).offset(2)
```

Since you can chain the querysets from other querysets, you can aggregate multiple operators in one
go as well.

```python
await User.query.filter(email__icontains="foo").limit(5).order_by("id")
```

### Batch size

When iterating asynchronously, you can set a chunk size for database reads:

```python
async for user in User.query.order_by("id").batch_size(100):
    ...
```

### Extra and reference selects

`extra_select()` adds SQLAlchemy expressions to the `SELECT` list.
`reference_select()` maps already-selected values back onto model attributes, including nested
related objects.

```python
import sqlalchemy

queryset = User.query.extra_select(sqlalchemy.literal(1).label("marker"))
queryset = queryset.reference_select({"score": "marker"})
```

Reference paths can target related models:

```python
queryset = Profile.query.select_related("user").reference_select(
    {"user": {"profile_name": "name"}, "user_name": "user__name"}
)
```

If you need the raw SQLAlchemy statement for subqueries or aggregates, use `as_select()`:

```python
user_select = await User.query.filter(is_active=True).as_select()
total = sqlalchemy.func.count().select().select_from(user_select.subquery())
```

### Order by

Classic SQL operation and you need to order results.


**Order by descending id and ascending email**

```python
users = await User.query.order_by("email", "-id")
```

**Order by ascending id and ascending email**

```python
users = await User.query.order_by("email", "id")
```

### Lookup

This is a broader way of searching for a given term. This can be quite an expensive operation so
**be careful when using it**.

```python
users = await User.query.lookup(term="gmail")
```

### Distinct

Applies SQL `DISTINCT` semantics to a queryset.

```python
users = await User.query.distinct()
users = await User.query.distinct("email")
```

Use `distinct(False)` to clear a previously applied distinct clause on a cloned queryset.

!!! Warning
    Not all SQL databases support `DISTINCT ON` fields equally. PostgreSQL does, but MySQL and
    SQLite have limitations here.
    Be careful to know and understand where this should be applied.

### Set operations

Saffier supports SQL set operations between querysets of the same model.

| Operation                   | Description                                 | SQL Equivalent |
|----------------------------|---------------------------------------------|----------------|
| `.union(qs2)`              | Combines both querysets, removing duplicates. | `UNION`        |
| `.union_all(qs2)`          | Combines both querysets, keeping duplicates.   | `UNION ALL`    |
| `.intersect(qs2)`          | Returns only rows appearing in both querysets. | `INTERSECT`    |
| `.intersect_all(qs2)`      | Uses the `ALL` variant when the backend supports it. | `INTERSECT ALL` |
| `.except_(qs2)`            | Returns rows from the first queryset that are not in the second. | `EXCEPT` |
| `.except_all(qs2)`         | Uses the `ALL` variant when the backend supports it. | `EXCEPT ALL` |

All set operations return a combined queryset, so outer queryset modifiers still apply to the
merged result:

```python
combined = User.query.filter(is_active=True).union(
    User.query.filter(is_staff=True)
)

rows = await combined.order_by("email").offset(5).limit(10)
```

The outer queryset supports the same result helpers you would use on a regular queryset:

```python
await combined.values(["id", "email"])
await combined.exists()
await combined.count()
await combined.first()
await combined.last()
```

The duplicate-preserving variants are also available directly:

```python
User.query.union_all(other_queryset)
User.query.intersect_all(other_queryset)
User.query.except_all(other_queryset)
```

!!! Warning
    Set operations require both querysets to use the same model, the same database connection,
    and the same selected column shape. If one side uses `only()` or `defer()`, the other side
    must project the same columns.

Deferred and reduced projections are preserved across combined querysets:

```python
q1 = User.query.filter(is_active=True).only("id", "email")
q2 = User.query.filter(is_staff=True).defer("last_login")

rows = await q1.union(q2).order_by("email").values(["id", "email"])
```

Like Edgy, Saffier applies ordering, offset, and limit to the outer combined result, not to the
individual branch orderings. Add an explicit `order_by()` when you need deterministic pagination or
comparison semantics.

### Row locking

Use `select_for_update()` to request row-level locking when running inside a transaction:

```python
async with database.transaction():
    users = await User.query.select_for_update(nowait=True).all()
```

### Select related

Returns a QuerySet that will “follow” foreign-key relationships, selecting additional
related-object data when it executes its query.

This is a performance booster which results in a single more complex query but means

later use of foreign-key relationships won’t require database queries.

A simple query:

```python
profiles = await Profile.query.select_related("user")
```

Or adding more operations on the top

```python
profiles = await Profile.query.select_related("user").filter(email__icontains="foo").limit(2)
```

## Returning results

### All

Returns all the instances.

```python
users = await User.query.all()
```

!!! Tip
    The all as mentioned before it automatically executed by **Saffier** if not provided and it
    can also be aggregated with other [queryset operations](#returning-querysets).


### Save

This is a classic operation that is very useful depending on which operations you need to perform.
Used to save an existing object in the database. Slighly different from the [update](#update) and
simpler to read.

```python
await User.query.create(is_active=True, email="foo@bar.com")

user = await User.query.get(email="foo@bar.com")
user.email = "bar@foo.com"

await user.save()
```

Now a more unique, yet possible scenario with a save. Imagine you need to create an exact copy
of an object and store it in the database. These cases are more common than you think but this is
for example purposes only.

```python
await User.query.create(is_active=True, email="foo@bar.com", name="John Doe")

user = await User.query.get(email="foo@bar.com")
# User(id=1)

# Making a quick copy
user.id = None
new_user = await user.save()
# user(id=2)
```

### Create

Used to create model instances.

```python
await User.query.create(is_active=True, email="foo@bar.com")
await User.query.create(is_active=False, email="bar@foo.com")
await User.query.create(is_active=True, email="foo@bar.com", first_name="Foo", last_name="Bar")
```

### Bulk get or create

Creates missing rows and reuses existing rows when matching `unique_fields`.

```python
users = await User.query.bulk_get_or_create(
    [
        {"name": "Alice", "language": "English"},
        {"name": "Bob", "language": "Portuguese"},
    ],
    unique_fields=["name", "language"],
)
```

Alias available: `bulk_select_or_insert`.

### Delete

Used to delete rows and return the number of deleted records.

```python
deleted = await User.query.filter(email="foo@bar.com").delete()
```

To execute per-instance delete hooks/signals during queryset deletion, use:

```python
deleted = await User.query.filter(is_active=False).delete(use_models=True)
```

Or directly in the instance.

```python
user = await User.query.get(email="foo@bar.com")

deleted = await user.delete()
```

Use `raw_delete()` when you want database-level deletion without model-level delete hooks:

```python
deleted = await User.query.filter(is_active=False).raw_delete()
```

### Update

You can update model instances by calling this operator.


```python
await User.query.filter(email="foo@bar.com").update(email="bar@foo.com")
```

Or directly in the instance.

```python
user = await User.query.get(email="foo@bar.com")

await user.update(email="bar@foo.com")
```

Or not very common but also possible, update all rows in a table.

```python
user = await User.query.update(email="bar@foo.com")
```

### Get

Obtains a single record from the database.

```python
user = await User.query.get(email="foo@bar.com")
```

You can mix the queryset returns with this operator as well.

```python
user = await User.query.filter(email="foo@bar.com").get()
```

### First

When you need to return the very first result from a queryset.

```python
user = await User.query.first()
```

You can also apply filters when needed.

### Last

When you need to return the very last result from a queryset.

```python
user = await User.query.last()
```

You can also apply filters when needed.

### Exists

Returns a boolean confirming if a specific record exists.

```python
exists = await User.query.filter(email="foo@bar.com").exists()
exists = await User.query.exists(email__isnull=True)
```

### Count

Returns an integer with the total of records.

```python
total = await User.query.count()
total = await User.query.count(email__icontains="@example.com")
```

### Contains

Returns true if the QuerySet contains the provided object.

```python
user = await User.query.create(email="foo@bar.com")

exists = await User.query.contains(instance=user)
```

### Values

Returns the model results in a dictionary like format.

```python
await User.query.create(name="John" email="foo@bar.com")

# All values
user = User.query.values()
users == [
    {"id": 1, "name": "John", "email": "foo@bar.com"},
]

# Only the name
user = User.query.values("name")
users == [
    {"name": "John"},
]
# Or as a list
# Only the name
user = User.query.values(["name"])
users == [
    {"name": "John"},
]

# Exclude some values
user = User.query.values(exclude=["id"])
users == [
    {"name": "John", "email": "foo@bar.com"},
]
```

The `values()` can also be combined with `filter`, `only`, `exclude` as per usual.

**Parameters**:

* **fields** - Fields of values to return.
* **exclude** - Fields to exclude from the return.
* **exclude_none** - Boolean flag indicating if the fields with `None` should be excluded.

### Values list

Returns the model results in a tuple like format.

```python
await User.query.create(name="John" email="foo@bar.com")

# All values
user = User.query.values_list()
users == [
    (1, "John" "foo@bar.com"),
]

# Only the name
user = User.query.values_list("name")
users == [
    ("John",),
]
# Or as a list
# Only the name
user = User.query.values_list(["name"])
users == [
    ("John",),
]

# Exclude some values
user = User.query.values(exclude=["id"])
users == [
    ("John", "foo@bar.com"),
]

# Flattened
user = User.query.values_list("email", flat=True)
users == [
    "foo@bar.com",
]
```

The `values_list()` can also be combined with `filter`, `only`, `exclude` as per usual.

**Parameters**:

* **fields** - Fields of values to return.
* **exclude** - Fields to exclude from the return.
* **exclude_none** - Boolean flag indicating if the fields with `None` should be excluded.
* **flat** - Boolean flag indicating the results should be flattened.

### Only

Returns the results containing **only** the fields in the query and nothing else.

```python
await User.query.create(name="John" email="foo@bar.com")

user = await User.query.only("name")
```

!!! Warning
    You can only use `only()` or `defer()` but not both combined or a `QuerySetError` is raised.

### Defer

Returns the results containing all the fields **but the ones you want to exclude**.

```python
await User.query.create(name="John" email="foo@bar.com")

user = await User.query.defer("name")
```

!!! Warning
    You can only use `only()` or `defer()` but not both combined or a `QuerySetError` is raised.

### Get or none

When querying a model and do not want to raise a [ObjectNotFound](../exceptions.md#doesnotfound) and
instead returns a `None`.

```python
user = await User.query.get_or_none(id=1)
```

## Useful methods

### Get or create

When you need get an existing model instance from the matching query. If exists, returns or creates
a new one in case of not existing.

Returns a tuple of `instance` and boolean `created`.

```python
user, created = await User.query.get_or_create(email="foo@bar.com", defaults={
    "is_active": False, "first_name": "Foo"
})
```

This will query the `User` model with the `email` as the lookup key. If it doesn't exist, then it
will use that value with the `defaults` provided to create a new instance.

!!! Warning
    Since the `get_or_create()` is doing a [get](#get) internally, it can also raise a
    [MultipleObjectsReturned](../exceptions.md#multipleobjectsreturned).


### Update or create

When you need to update an existing model instance from the matching query. If exists, returns or creates
a new one in case of not existing.

Returns a tuple of `instance` and boolean `created`.

```python
user, created = await User.query.update_or_create(email="foo@bar.com", defaults={
    "is_active": False, "first_name": "Foo"
})
```

This will query the `User` model with the `email` as the lookup key. If it doesn't exist, then it
will use that value with the `defaults` provided to create a new instance.

!!! Warning
    Since the `get_or_create()` is doing a [get](#get) internally, it can also raise a
    [MultipleObjectsReturned](../exceptions.md#multipleobjectsreturned).


### Bulk create

When you need to create many instances in one go, or `in bulk`.

```python
await User.query.bulk_create([
    {"email": "foo@bar.com", "first_name": "Foo", "last_name": "Bar", "is_active": True},
    {"email": "bar@foo.com", "first_name": "Bar", "last_name": "Foo", "is_active": True},
])
```

### Bulk update

When you need to update many instances in one go, or `in bulk`.

```python
await User.query.bulk_create([
    {"email": "foo@bar.com", "first_name": "Foo", "last_name": "Bar", "is_active": True},
    {"email": "bar@foo.com", "first_name": "Bar", "last_name": "Foo", "is_active": True},
])

users = await User.query.all()

for user in users:
    user.is_active = False

await User.query.bulk_update(users, fields=['is_active'])
```

## Operators

There are sometimes the need of adding some extra conditions like `AND`, or `OR` or even the `NOT`
into your queries and therefore Saffier provides a simple integration with those.

Saffier provides the [and_](#and), [or_](#or) and [not_](#not) operators directly for you to use, although
this ones come with a slighly different approach.

For all the examples, let us use the model below.

```python
{!> ../docs_src/queries/clauses/model.py !}
```

### SQLAlchemy style

Since Saffier is built on the top of SQL Alchemy core, that also means we can also use directly that
same functionality within our queries.

In other words, uses the [SQLAlchemy style](#sqlalchemy-style).

!!! Warning
    The `or_`, `and_` and `not_` do not work with [related](./related-name.md) operations and only
    directly with the model itself.

This might sound confusing so let us see some examples.

#### AND

As the name suggests, you want to add the `AND` explicitly.

```python
{!> ../docs_src/queries/clauses/and.py !}
```

As mentioned before, applying the [SQLAlchemy style](#sqlalchemy-style) also means you can do this.

```python
{!> ../docs_src/queries/clauses/and_two.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/and_m_filter.py !}
```

#### OR

The same principle as the [and_](#and) but applied to the `OR`.

```python
{!> ../docs_src/queries/clauses/or.py !}
```

As mentioned before, applying the [SQLAlchemy style](#sqlalchemy-style) also means you can do this.

```python
{!> ../docs_src/queries/clauses/or_two.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/or_m_filter.py !}
```

#### NOT

This is simple and direct, this is where you apply the `NOT`.

```python
{!> ../docs_src/queries/clauses/not.py !}
```

As mentioned before, applying the [SQLAlchemy style](#sqlalchemy-style) also means you can do this.

```python
{!> ../docs_src/queries/clauses/not_two.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/not_m_filter.py !}
```

### Saffier Style

This is the most common used scenario where you can use the [related](./related-name.md) for your
queries and all the great functionalities of Saffier while using the operands.

!!! Tip
    The same way you apply the filters for the queries using the [related](./related-name.md), this
    can also be done with the **Saffier style** but the same cannot be said for the
    [SQLAlchemy style](#sqlalchemy-style-1). So if you want to leverage the full power of Saffier,
    it is advised to go Saffier style.

#### AND

The `AND` operand with the syntax is the same as using the [filter](#filter) or any queryset
operatator but for visualisation purposes this is also available in the format of `and_`.

```python
{!> ../docs_src/queries/clauses/style/and_two.py !}
```

With multiple parameters.

```python
{!> ../docs_src/queries/clauses/style/and.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/style/and_m_filter.py !}
```

#### OR

The same principle as the [and_](#and-1) but applied to the `OR`.

```python
{!> ../docs_src/queries/clauses/style/or.py !}
```

With multiple `or_` or nultiple parametes in the same `or_`

```python
{!> ../docs_src/queries/clauses/style/or_two.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/style/or_m_filter.py !}
```

#### NOT

The `not_` as the same principle as the [exclude](#exclude) and like the [and](#and-1), for
representation purposes, Saffier also has that function.

```python
{!> ../docs_src/queries/clauses/style/not.py !}
```

With multiple `not_`.

```python
{!> ../docs_src/queries/clauses/style/not_two.py !}
```

And you can do nested `querysets` like multiple [filters](#filter).

```python
{!> ../docs_src/queries/clauses/style/not_m_filter.py !}
```

Internally, the `not_` is calling the [exclude](#exclude) and applying the operators so this is
more for *cosmetic* purposes than anything else, really.

## Blocking Queries

What happens if you want to use Saffier with a blocking operation? So by blocking means `sync`.
For instance, Flask does not support natively `async` and Saffier is an async agnotic ORM and you
probably would like to take advantage of Saffier but you want without doing a lot of magic behind.

Well, Saffier also supports the `run_sync` functionality that allows you to run the queries in
*blocking* mode with ease!

### How to use

You simply need to use the `run_sync` functionality from Saffier and make it happen almost immediatly.

```python
from saffier import run_sync
```

All the available functionalities of Saffier run within this wrapper without extra syntax.

Let us see some examples.

**Async mode**

```python
await User.query.all()
await User.query.filter(name__icontains="example")
await User.query.create(name="Saffier")
```

**With run_sync**

```python
from saffier import run_sync

run_sync(User.query.all())
run_sync(User.query.filter(name__icontains="example"))
run_sync(User.query.create(name="Saffier"))
```

If synchronous code also needs to manage registry connection lifecycle, wrap it with
`Registry.with_async_env()`:

```python
with models.with_async_env():
    run_sync(models.create_all())
    run_sync(User.query.create(name="Saffier"))
```

[model]: ../models.md
[managers]: ../managers.md
