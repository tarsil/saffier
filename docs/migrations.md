# Migrations

You will almost certainly need to be using a database migration tool to make sure you manage
your incremental database changes properly.

Saffier being on the top of SQLAlchemy core means that we stringly recommend you to use
[Alembic](https://alembic.sqlalchemy.org/en/latest/) which is also from the same author.

Now, using alembic is pretty much staright forward as it is expecting details that you can already
provide such as `database_url` but what about the `metadata`?

### Metadata

Saffier still has access to the same metadata needed to generate the migrations with alembic and
that is where [registry](./registry.md) plays a big role.

Inside your registry you can simply do:

```python hl_lines="7"
import saffier
from saffier import Database, Registry

database = Database("drier://user:pass@localhost/dbname")
models = Registry(database=database)

metadata = models.metadata
```

This metadata is what it can then be passed onto Alembic's configuration.

Alembic has a set of configurations like the `env.py` that you should be changing. Those details
can be found in the docs.

**Let's see an example**

Assuming you installed alembic and started the migrations:

```shell
$ pip install alembic
$ alembic init migrations
```

In `alembic.ini` remove the following line:

```shell
sqlalchemy.url = driver://user:pass@localhost/dbname
```

In the `migrations/env.py`, set `sqlalchemy.url` key and `target_metadata` variable. Something like
this and using the `metadata` from the previous example:

```python hl_lines="7"
import os

# Alembic Config object.
config = context.config

config.set_main_option(sqlalchemy.url, str(os.environ.get("DATABASE_URL")))
target_metadata = metadata # from the `metadata = models.metadata`

...
```

Then run the usual Alembic commands, like creating the first revision:

```shell
alembic revision -m "Create users table"
```

The rest of the alembic instructions and how to use it is inside their documentation.

