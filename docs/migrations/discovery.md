# Application Discovery

Saffier has many different ways of understanding the commands, one is via
[environment variables](#environment-variables) and another is via [auto discovery](#auto-discovery).

## Auto Discovery

If you are familiar with other frameworks like Django, you are surely familiar with the way the
use the `manage.py` to basically run every command internally.

Although not having that same level, Saffier does a similar job by having "a guess" of what
it should be and throws an error if not found or if no [environment variables or --app](#environment-variables)
are provided.

**The application discovery works as an alternative to providing the `--app` or a `SAFFIER_DEFAULT_APP` environment variable**.

So, what does this mean?

This means if **you do not provide an --app or a SAFFIER_DEFAULT_APP**, Saffier will try to find the
application for you automatically.

Let us see a practical example of what does this mean.

Imagine the following folder and file structure:

```shell hl_lines="16" title="myproject"
.
├── Makefile
└── myproject
    ├── __init__.py
    ├── apps
    │   ├── __init__.py
    ├── configs
    │   ├── __init__.py
    │   ├── development
    │   │   ├── __init__.py
    │   │   └── settings.py
    │   ├── settings.py
    │   └── testing
    │       ├── __init__.py
    │       └── settings.py
    ├── main.py
    ├── tests
    │   ├── __init__.py
    │   └── test_app.py
    └── urls.py
```

!!! Tip
    The `application` can be anything from Esmerald, Starlette, Sanic and even FastAPI.

The structure above of `myproject` has a lot of files and the one higlighted is the one that
contains the application object with the [Migration](./migrations.md#migration) from Saffier.

### How does it work?

When no `--app` or no `SAFFIER_DEFAULT_APP` environment variable is provided, Saffier will
**automatically look for**:

* The current directory where `saffier` is being called contains a file called:
    * **main.py**
    * **app.py**
    * **application.py**

    !!! Warning
        **If none of these files are found**, Saffier will look **at the first children nodes, only**,
        and repeats the same process. If no files are found then throws an `CommandEnvironmentError`
        exception.

* Once one of those files is found, Saffier will analised the type of objects contained in the
module and will check if any of them contains the `Migration` object attached and return it.

* If Saffier understand that none of those objects contain the `Migration`, it will
do one last attempt and try to find specific function declarations:
    * **get_application()**
    * **get_app()**

This is the way that Saffier can `auto discover` your application.

!!! Note
    Flask has a similar pattern for the functions called `create_app`. Saffier doesn't use the
    `create_app`, instead uses the `get_application` or `get_app` as a pattern as it seems cleaner.


## Environment variables

When generating migrations, Saffier **expects at least one environment variable to be present**.

* **SAFFIER_DATABASE_URL** - The database url for your database.

The reason for this is because Saffier is agnostic to any framework and this way it makes it easier
to work with the `migrations`.

Also, gives a clean design for the time where it is needed to go to production as the procedure is
very likely to be done using environment variables.

**This variable must be present**. So to save time you can simply do:

```
$ export SAFFIER_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/my_database
```

Or whatever connection string you are using.

Alternatively, you can simply pass `--app` as a parameter with the location of your application
instead.

Example:

```shell
$ saffier --app myproject.main:app init
```

## How to use and when to use it

Previously it was used a folder structure as example and then an explanation of how Saffier would
understand the auto discovery but in practice, how would that work?

**This is applied to any command within Saffier**.

Let us see again the structure, in case you have forgotten already.

```shell hl_lines="20" title="myproject"
.
├── Makefile
└── src
    ├── __init__.py
    ├── apps
    │   ├── accounts
    │   │   ├── directives
    │   │   │   ├── __init__.py
    │   │   │   └── operations
    │   │   │       └── __init__.py
    ├── configs
    │   ├── __init__.py
    │   ├── development
    │   │   ├── __init__.py
    │   │   └── settings.py
    │   ├── settings.py
    │   └── testing
    │       ├── __init__.py
    │       └── settings.py
    ├── main.py
    ├── tests
    │   ├── __init__.py
    │   └── test_app.py
    └── urls.py
```

The `main.py` is the file that contains the saffier migration. A file that could look like
this:

```python title="myproject/src/main.py"
{!> ../docs_src/commands/discover.py !}
```

This is a simple example with two endpoints, you can do as you desire with the patterns you wish to
add and with any desired structure.

What will be doing now is run the following commands using the [auto discovery](#auto-discovery)
and the [--app or SAFFIER_DEFAULT_APP](#environment-variables):

* **init** - Starts the migrations and creates the migrations folder.
* **makemigrations** - Generates the migrations for the application.

We will be also executing the commands inside `myproject`.

**You can see more information about these [commands](./migrations.md), including**
**parameters, in the next section.**

### Using the auto discover

#### init

##### Using the auto discover

```shell
$ saffier init
```

Yes! Simply this and because the `--app` or a `SAFFIER_DEFAULT_APP` was provided, it triggered the
auto discovery of the application that contains the saffier information.

Because the application is inside `src/main.py` it will be automatically discovered by Saffier as
it followed the [discovery pattern](#how-does-it-work).

##### Using the --app or SAFFIER_DISCOVERY_APP

This is the other way to tell Saffier where to find your application. Since the application is
inside the `src/main.py` we need to provide the proper location is a `<module>:<app>` format.

###### --app

With the `--app` flag.

```shell
$ saffier --app src.main:app init
```

###### SAFFIER_DEFAULT_APP

With the `SAFFIER_DEFAULT_APP`.

Export the env var first:

```shell
$ export SAFFIER_DEFAULT_APP=src.main:app
```

And then run:

```shell
$ saffier init
```

#### makemigrations

You can see [more details](./migrations.md#migrate-your-database) how to use it.

It is time to run this command.

##### Using the auto discover

```shell
$ saffier makemigrations
```

Again, same principle as before because the `--app` or a `SAFFIER_DEFAULT_APP` was provided,
it triggered the auto discovery of the application.

##### Using the --app or SAFFIER_DISCOVERY_APP

###### --app

With the `--app` flag.

```shell
$ saffier --app src.main:app makemigrations
```

###### SAFFIER_DEFAULT_APP

With the `SAFFIER_DEFAULT_APP`.

Export the env var first:

```shell
$ export SAFFIER_DEFAULT_APP=src.main:app
```

And then run:

```shell
$ saffier makemigrations
```
