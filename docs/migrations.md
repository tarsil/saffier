# Migrations

You will almost certainly need to be using a database migration tool to make sure you manage
your incremental database changes properly.

Saffier being on the top of SQLAlchemy core means that we can leverage that within the internal
migration tool.

Saffier provides an internal migration tool that makes your life way easier when it comes to manage
models and corresponding migrations.

Heavily inspired by the way Flask-Migration approached the problem, Saffier took it to the next
level and makes it framework agnostic, which means you can use it **anywhere**.

## Structure being used for this document

For the sake of this document examples and explanations we will be using the following structure to
make visually clear.

```shell
.
└── myproject
    ├── __init__.py
    ├── apps
    │   ├── __init__.py
    │   └── accounts
    │       ├── __init__.py
    │       ├── tests.py
    │       └── v1
    │           ├── __init__.py
    │           ├── schemas.py
    │           ├── urls.py
    │           └── views.py
    ├── configs
    │   ├── __init__.py
    │   ├── development
    │   │   ├── __init__.py
    │   │   └── settings.py
    │   ├── settings.py
    │   └── testing
    │       ├── __init__.py
    │       └── settings.py
    ├── main.py
    ├── serve.py
    ├── utils.py
    ├── tests
    │   ├── __init__.py
    │   └── test_app.py
    └── urls.py
```

## Migration

This is the object that Saffier requires to make sure you can manage the migrations in a consistent,
clean and simple a manner. Much like Django migrations type of feeling.

This `Migration` class is not depending of any framework specifically, in fact, Saffier makes sure
when this object is created, it will plug it into any framework you desire.

This makes Saffier unique and extremely flexible to be used within any of the Frameworks out there,
such as [Esmerald](https://esmerald.dymmond.com), Starlette, FastAPI, Sanic... You choose.

```python
from saffier import Migration
```

### Parameters

The parameters availabe when using instantiating a [Migrate](#migration) object are the following:

* **app** - The application instance. Any application you want your migrations to be attached to.
* **registry** - The registry being used for your models. The registry **must be** an instance
of `saffier.Registry` or an `AssertationError` is raised.
* **directory** - The name of the directory where the migrations will be placed. Be careful when
overriding this value.

    <sup>Default: `migrations`</sup>

* **compare_type** - Flag option that configures the automatic migration generation subsystem 
to detect column type changes.

    <sup>Default: `True`</sup>

* **render_as_batch** - This option generates migration scripts using batch mode, an operational
mode that works around limitations of many ALTER commands in the SQLite database by implementing
a "move and copy" workflow. Enabling this mode should make no difference when working with other
databases.

    <sup>Default: `True`</sup>

* **kwargs** - A python dictionary with any context variables to be added to alembic.

    <sup>Default: `None`</sup>

### How to use it

Using the [Migration](#migration) class is very simple in terms of requirements. In the
[tips and tricks](./tips-and-tricks.md) you can see some examples in terms of using the
[LRU cache technique](./tips-and-tricks.md#the-lru-cache). If you haven't seen it,
it is recommended you to have a look.

For this examples, we will be using the same approach.

Assuming you have a `utils.py` where you place your information about the database and
[registry](./registry.md).

Something like this:

```python title="my_project/utils.py" hl_lines="6-9"
{!> ../docs_src/migrations/lru.py !}
```

This will make sure we don't create objects everything we need to import them anywhere else in the
code. Nice technique and quite practical.

Now that we have our details about the database and registry, it is time to use the
[Migration](#migration) object in the application.

#### Using Esmerald

```python title="my_project/main.py" hl_lines="9 12 32 38"
{!> ../docs_src/migrations/migrations.py !}
```

#### Using FastAPI

As mentioned before, Saffier is framework agnostic so you can also use it in your FastAPI
application.

```python title="my_project/main.py" hl_lines="6 9 29 33"
{!> ../docs_src/migrations/fastapi.py !}
```

#### Using Starlette

The same goes for Starlette.

```python title="my_project/main.py" hl_lines="6 9 29 33"
{!> ../docs_src/migrations/starlette.py !}
```

#### Using other frameworks

I believe you got the idea with the examples above, It was not specified any special framework
unique-like parameter that demanded special attention, just the application itself.

This means you can plug something else like Quart, Ella or even Sanic... Your pick.

