# ManyToMany

In a lot of projects out there you see cases where a ManyToMany would be helpful. Django for example,
has that defined as internal model when a field is declared.

In theory, when designing a database, the `ManyToMany` does not exist and it is not possible in
a relational system.

What happens internally is the creation of an intermediary table that links the many to many tables.

## How does it work

As mentioned before, a many to many it is not possible in a relational database, instead, an
intermediary table needs to be created and connect the tables for the said many to many.

This is exactly what saffier does with the [ManyToMany][many_to_many] automatically.

### Quick note

The `ManyToMany` or `ManyToMany` accepts both [Model](../models.md) and string as
a parameter for the `to`.

**Example**

```python
# Using the model directly
class Profile(saffier.Model):
    users = saffier.ManyToMany(User)

# Using a string
class Profile(saffier.Model):
    users = saffier.ManyToMany("User")
```

### Operations

With the many to many you can perform all the normal operations of searching from normal queries
to the [related name][related_name] as per normal search.

ManyToMany allows two different methods when using it.

* `add()` - Adds a record to the ManyToMany.
* `add_many()` - Adds multiple records to the ManyToMany in one call.
* `remove()` - Removes a record to the ManyToMany.
* `remove_many()` - Removes multiple records from the ManyToMany in one call.

Reverse related names generated from the through model expose the same helpers, so you can mutate
the relation from either side.

Let us see how it looks by using the following example.

```python hl_lines="17"
{!> ../docs_src/queries/manytomany/example.py !}
```

#### add()

You can now add teams to organisations, something like this.

```python hl_lines="6-7"
blue_team = await Team.query.create(name="Blue Team")
green_team = await Team.query.create(name="Green Team")
organisation = await Organisation.query.create(ident="Acme Ltd")

# Add teams to the organisation
organisation.teams.add(blue_team)
organisation.teams.add(green_team)
```

#### add_many()

When you already have multiple related instances, you can stage all of them in a single
call and keep the result list for downstream assertions or prefetch flows.

```python
await organisation.teams.add_many(blue_team, green_team, red_team)
```

#### remove_many()

You can also remove multiple related instances in one call.

```python
await organisation.teams.remove_many(blue_team, red_team)
```

#### remove()

You can now remove teams from organisations, something like this.

```python hl_lines="12-13"
blue_team = await Team.query.create(name="Blue Team")
green_team = await Team.query.create(name="Green Team")
red_team = await Team.query.create(name="Red Team")
organisation = await Organisation.query.create(ident="Acme Ltd")

# Add teams to organisation
organisation.teams.add(blue_team)
organisation.teams.add(green_team)
organisation.teams.add(red_team)

# Remove the teams from the organisation
organisation.teams.remove(red_team)
organisation.teams.remove(blue_team)
```

If the reverse side is unique, `remove()` can omit the child and Saffier will remove the single
linked row.

```python
await track.track_albumtrack.remove()
```

#### Querying through many-to-many paths

Many-to-many paths can be used directly in queryset filters and `Q(...)` expressions.

```python
teams = await Organisation.query.filter(teams__name__icontains="blue").distinct("id")

users = await User.query.filter(
    saffier.Q(products__name__icontains="soap")
    | saffier.Q(products__categories__name="food")
).distinct("id")
```

The same traversal rules apply to reverse many-to-many paths and to longer mixed paths that
cross foreign keys.


#### Related name

The same way you define [related names][related_name] for foreign keys, you can do the same for
the [ManyToMany][many_to_many].

When a `related_name` is not defined, Saffier will automatically generate one with the following
format:

```shell
<table-to-many2many>_<through-model-name>s_set
```

If the many-to-many field is declared with `unique=True`, the generated reverse related name is
singular and omits the trailing `s_set`.

##### Example without related name

```python
{!> ../docs_src/queries/manytomany/no_rel.py !}
```

```python
{!> ../docs_src/queries/manytomany/no_rel_query_example.py !}
```

As you can see, because no `related_name` was provided, it defaulted to `team_organisationteams_set`.

### Embedded through rows

`ManyToManyField(..., embed_through="membership")` returns the related model instance and attaches
the intermediate row on `membership`.

```python
team = await organisation.teams.get(name="Blue Team")
assert team.membership.organisation.pk == organisation.pk
```

The embedded alias is also available in queryset filters.

```python
team = await organisation.teams.filter(membership__team__name="Blue Team").get()
```


##### Example with related name

```python hl_lines="17"
{!> ../docs_src/queries/manytomany/example.py !}
```

!!! Tip
    The way you can query using the [related name][related_name] are described in detail in the
    [related name][related_name] section and has the same level of functionality as per normal
    foreign key.

You can now query normally, something like this.

```python hl_lines="11"
{!> ../docs_src/queries/manytomany/query_example.py !}
```


[many_to_many]: ../fields.md#manytomanyfield
[related_name]: ./related-name.md
