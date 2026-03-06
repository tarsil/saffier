# CLI Commands

Saffier ships with a CLI for migrations, shell usage, and schema inspection.

This page summarizes the command surface and typical flows.

## Before Running Commands

Most commands need an application context.

Provide it via:

* `--app path.to.module:app`
* `SAFFIER_DEFAULT_APP=path.to.module:app`

See [Discovery](../migrations/discovery.md) for details.

## Command Families

| Goal | Typical Commands |
| --- | --- |
| Setup migration repository | `list-templates`, `init` |
| Generate revision files | `revision`, `makemigrations`, `merge`, `edit` |
| Apply or revert revisions | `migrate`, `downgrade`, `stamp` |
| Inspect migration state | `current`, `heads`, `branches`, `history`, `show`, `check` |
| Runtime utilities | `shell`, `inspectdb` |

## Migration Bootstrap

### `saffier list-templates`

Show available migration templates.

```shell
$ saffier list-templates
```

Built-in templates:

* `default`
* `plain`
* `url`
* `sequencial`

### `saffier init`

Create migration repository files.

```shell
$ saffier init
$ saffier init -t plain
$ saffier init -t url
$ saffier init -t sequencial
```

## Migration Generation

### `saffier revision`

Create a new revision script.

```shell
$ saffier revision -m "Add status column"
$ saffier revision --autogenerate -m "Sync models"
```

### `saffier makemigrations`

Alias for `saffier revision --autogenerate`.

```shell
$ saffier makemigrations
$ saffier makemigrations -m "Initial schema"
```

### `saffier merge`

Merge multiple heads.

```shell
$ saffier merge -m "Merge heads" <rev_a> <rev_b>
```

### `saffier edit`

Edit a revision from the CLI.

```shell
$ saffier edit head
```

## Migration Execution

### `saffier migrate`

Upgrade to `head` (or a specific revision).

```shell
$ saffier migrate
$ saffier migrate <revision>
```

### `saffier downgrade`

Rollback to an older revision.

```shell
$ saffier downgrade -1
$ saffier downgrade <revision>
```

### `saffier stamp`

Set the revision marker without applying migrations.

```shell
$ saffier stamp head
```

## Migration Introspection

```shell
$ saffier current
$ saffier heads
$ saffier branches
$ saffier history
$ saffier show head
$ saffier check
```

## Runtime Utilities

### `saffier shell`

Start an interactive shell.

```shell
$ saffier shell
$ saffier shell --kernel ptpython
```

### `saffier inspectdb`

Reflect an existing database into models.

```shell
$ saffier inspectdb --database "postgres+asyncpg://user:pass@localhost:5432/my_db"
```

## Recommended Flow

1. `saffier init` (once)
2. `saffier makemigrations`
3. `saffier migrate`
4. Repeat 2-3 as models evolve

## See Also

* [Migrations](../migrations/migrations.md)
* [Discovery](../migrations/discovery.md)
* [Shell](../shell.md)
* [Inspect DB](../inspectdb.md)
