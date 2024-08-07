---
hide:
  - navigation
---

# Release Notes

## 1.4.2

### Changed

- Add integration with the newly `databasez` 0.8.5+.
- Internal refactor of the registry.

### Fixed

- CI integration.

## 1.4.1

### Added

- Support for `list` and `tuples` as a type for [model_apps](./migrations/migrations.md#using-the-model_apps).

## 1.4.0

### Added

- Support for `model_apps` inside the `Migrate` object allowing
global discovery by application. This will make sure all apps will be properly
inspected.
- Add documentation about the new [model_apps](./migrations/migrations.md#using-the-model_apps).

### Changed

- Upgrade internal requirements.

## 1.3.7

### Changed

- New lazy loading settings system making it more unique and dynamic working side by side
with `dymmond-settings`.

## 1.3.6

### Changed

- Update internal `dymmond-settings` minimum requirement.

## 1.3.5

### Changed

**BREAKING CHANGE**

Due to some internal compatibilities, Saffier is rolling back to `SAFFIER_SETTINGS_MODULE`
from `SETTINGS_MODULE`

- `SETTINGS_MODULE` was renamed to `SAFFIER_SETTINGS_MODULE`.

## 1.3.4

### Changed

- Update internal anyio dependency.

## 1.3.3

### Changed

- Upgrade internal requirements.

### Fixed

- `auto_now` and `auto_now_add` on `save()` and `update()` wasn't only updating the
field with `auto_now`.
- Extraction of the default field for `date` and `datetime`.

## 1.3.2

### Fixed

- The way settings default is loaded. [#124](https://github.com/tarsil/saffier/pull/124) by [@vvanglro](https://github.com/vvanglro)

## 1.3.1

### Fixed

- Fix default for `SAFFIER_SETTINGS_MODULE` if nothing is provided.

## 1.3.0

### Added

- Added new experimental [activate_schema](./tenancy/saffier.md#using-with-activate_schema) for tenant models using the `using` queryset operator.
- Support for ManyToMany to accept strings to the `to` attribute.
- Support for new queryset operations [only()](./queries/queries.md#only) and [defer](./queries/queries.md#defer).
- Intenal `ModelProxy` allowing to manipulate objects querysets such as `only` and `defer`.
- Support for [secrets](./queries/secrets.md) and secret queryset.

### Changed

- Increased maximum of 63 characters the name of the index/unique.
- ModelRow now contains private methods.
- Updated documentation with missing [select_related](./queries/queries.md#load-the-foreign-keys-beforehand-with-select-related).
- Updated documentation for [access of data via foreign keys](./relationships.md#access-the-foreign-key-values-directly-from-the-model).
- Deprecating internal settings from Pydantic in favour of [Dymmond Settings](https://settings.dymmond.com).

#### Breaking changes

Saffier now uses  [Dymmond Settings](https://settings.dymmond.com) which this simlpy affects the way the
settings module is loaded. Prior to version 1.3.0 it was like this:

```python
SAFFIER_SETTINGS_MODULE=...
```

**From version 1.3.0 is**:

```python
SAFFIER_SETTINGS_MODULE=...
```

The rest remains as it. More information about [how to use it in the official documentation](https://settings.dymmond.com/#how-to-use-it_1).

### Fixed

- Multiple join tables were not generating the complete join statement when using `select_related`.
- Fixed metaclass for TenantMixin making sure all the queries are correctly pointing
to the right tenant.
- When generating a many to many through model, the maximum length is enforced to be 63 characters.
- Object discovery for intellisense.
- Allow `ManyToMany` to also accept a string as a parameter for the `to`.

## 1.2.0

### Added

- Support for `sync` queries. This will enable Edgy to run in blocking frameworks like
Flask, bottle or any other by using the newly added [run_sync](./queries/queries.md#blocking-queries).

### Fixed

- Fixed multi tenancy from contrib.
- Fixed `using` where schema name was raising a not found reference for foreign key
when querying the tenant.

## 1.1.0

### Added

- Support for [`or_`, `and_` and `not_`](./queries/queries#saffier-style) for SQLAlchemy style queries and Edgy syntax sugar queries.

### Changed

- `inspectdb` is now handled by an independent isolated called `InspectDB`.
- Updated internal support for `databasez` 0.7.0 and this fixes the URL parsing errors for complex passwords
caused by the `urlsplit`.

### Fixed

- `server_default` does not raise a `ValueError`.
- `server_default` added as validation for nullable.

!!! Warning
	This could impact your migrations, so the advise would be to generate a new migration
	after upgrading to the new version of Edgy to make sure the database reflects the proper
	nullables/non-nullable fields.


## 1.0.2

### Added

- `inspectdb` allowing to generate `saffier.ReflectModel` from the database.

### Changed

- Added `name` for `edgy.UniqueConstraint` allowing unique custom names for the `unique_together`.
- `max_name_length` in the datastuctures changed to `__max_name_length__` and `ClassVar`.

## 1.0.1

### Changed

- Add [API Reference](http://saffier.tarsild.io/references/).
- Update base requirements.

### Fixed

- `Database` object docstring.

## 1.0.0

### Added

- Support for Python 3.12

### Changed

- Update base requirements.

## 0.18.0

### Added

- New [Prefetch](./queries/prefetch.md) support allowing to simultaneously load nested data onto models.
- New [Signal](./signals.md) support allowing to "listen" to model events upon actions being triggered.

### Changed

- Updated pydantic and alembic

## 0.17.1

### Fixed

-  DeclarativeModel generating internal mappings names was breaking for class objects.

## 0.17.0

### Added

- Multi tenancy support by updating the registry and allowing to create the multi schema.
- Add new `using(schema=...)` and `using_with_db(database=..., schema=...)` to querysets.
- Add support for `create_schema` and `drop_schema` via registry.
- Add support to `get_default_schema` from the `registry.schema`.
- Documentation for [tenancy](./tenancy/saffier.md).
- Improved the documentation for [schemas](./registry.md#schemas).
- Added a new parameter `extra` to registry allowing to pass a Dict like object containing more database connections. This is an alternative to the registries.
- Improved documentation for [registry](./registry.md#extra) explaining how to use the extra parameters.
and query them.
- Added a new ConnectionConfig TypedDict for the registry extra.

### Changed

- Update the `build` for `Model` and `ReflectModel` to allow passing the schema.

### Fixed

- Registry `metaclass` wasn't reflecting 100% the schema being passed into the metadata and therefore, querying the database public schema.

## 0.16.0

### Changed

- Updated versions of the requirements to the latest.
- Internal file structure
- **Breaking change**. Before for fields the import was `from saffier.db.models.fields import ...` and that
was now changed to `from saffier.db.fields import ...`

### Added

- `values()` and `values_list()` to the queryset.

### Fixed

- ConfigDict in settings.

## 0.15.0

### Added

- [SaffierExtra](./extras.md) class allowing the use of Saffier tools without depending on the `Migrate` object.

## 0.14.2

### Fixed

- AsyncIO event loop blocking the reflection.

## 0.14.1

### Fixed

- Remove super init from `Registry`.

## 0.14.0

### Changed

- Update Saffier core to start using [Pydantic 2.0](https://docs.pydantic.dev/2.0/) and improved
performance.

!!! Note
    This is a massive performance improvement done by Pydantic that is now compiled in Rust. This
    bring a whole new level of performance to Saffier as well.

!!! Warning
    To use this version of Saffier with Esmerald, until it is announced compatibility with pydantic 2.0 with Esmerald, it is recommended to use saffier prior to this release.

## 0.13.0

### Changed

- `fields` are now imported in a different path. **This is a breaking change**. [PR #62](https://github.com/tarsil/saffier/pull/63) by [@tarsil](https://github.com/tarsil/)

**Before**

```python
from saffier import fields
```

**Now**

```python
from saffier.db import fields
```

### Added

- Added `server_default` option for fields allowing to specify if the value should be generated from the DB and how to.
- Added support for `save()` of the model. [PR #62](https://github.com/tarsil/saffier/pull/62) by [@tarsil](https://github.com/tarsil/)

## 0.12.0

### Added

- New version of the [`declarative()`](./declarative-models.md).
PR [#60](https://github.com/tarsil/saffier/pull/60)  by [@tarsil](https://github.com/tarsil).
- `ManyToMany` and `OneToOne` added as alternatives to `ManyToManyField` and `OneToOneField`.
The latter will always exist but you can also import the `ManyToMany` and `OneToOne` as alternative
instead.

### Fixed

- Registry now allowing the `lru_caching` to happen properly.

## 0.11.0

### Added

- [`declarative()`](./declarative-models.md) to the models, allowing generating model types of SQLAlchemy declarative base.
PR [#58](https://github.com/tarsil/saffier/pull/58) by [@tarsil](https://github.com/tarsil).

## 0.10.2

### Added

- `comment` option for the fields. PR [#57](https://github.com/tarsil/saffier/pull/57) by [@tarsil](https://github.com/tarsil).

## 0.10.1

### Changed

- Minor update of the base of databasez package. PR [#56](https://github.com/tarsil/saffier/pull/56) by [@tarsil](https://github.com/tarsil).

## 0.10.0

### Changed

- Updated to the latest version of pydantic making sure all the fixes are in place.

## 0.9.0

### Added

- Add protocols to Queryset.
- Add Protocols to Related names
- Support for the new [ManyToManyField](./fields.md##manytomanyfield)
- Documentation for [ManyToManyField](./queries/many-to-many.md)

## 0.8.0

### Changed

- Updated [relationships](./relationships.md) document with more examples regarding
multiple foreign key declarations.

### Added

- `contains` method to queryset allowing to query if a given model or reflected model exists in the
queryset.
- `related_name` is now supported on `ForeignKey` allowing transverse queries.
- Allow reverse queries using nested fields.
- `on_update` for ForeignKey and OneToOne fields
- Multiple ForeignKeys to the same table is now possible.
- [Related Name](./queries/related-name.md) document added
- Nested queries using related_name

## 0.7.4

### Fixed

- Removed `nested_asyncio` causing infinite loops.

## 0.7.3

### Added

- `postgresql` Typo in requirement installation.

## 0.7.2

### Added

- `db_schema` - Added Registry objects of the metadata.

## 0.7.1

### Fixed

- `Lifespan` event on shell returning async manager.

## 0.7.0

### Changed

- Renamed `saffier-admin` to `saffier`.
- Deprecate `saffier-admin`. Now you can simply call `saffier` with the same commands
as before.

### Added

- New `shell` command that allows interactive shell with saffier models.
- New `SAFFIER_SETTINGS_MODULE` allowing to create and pass specific and unique settings
to any saffier instance.
- Added support for `ipython` and `ptpython` for shell access via `saffier`.

### Fixed

- Linting and formatting issues with Ruff.
- Bug with ReflectModel. A ReflectModel might not need all the fields from the database and the mapping should reflect that.
- `run_until_complete` issues fixed with `nest_asyncio`.

## 0.6.1

### Fixed

- `UUIField` generations with Alembic.

## 0.6.0

### Added

- Support for SQLAlchemy 2.

### Changed

- Moved from `databases` to its fork `databasez` and updated internal references.
- `DatabaseClient` is now being directly used from [Databasez test client](https://databasez.tarsild.io/test-client/).

### Fixed

- Updated requirements.

## 0.5.0

### Changed

- Updated requirements to support Esmerald >= 1.1.0 for testing.
- Updated testing and docs requirements.

### Added

- Metaclass option to support database tables reflection. Allowing reading tables from existing database. [35](https://github.com/tarsil/saffier/pull/35)
- Documentation regarding the reflection of tables. [#37](https://github.com/tarsil/saffier/pull/37)

### Fixed

- Typos in documentation

## 0.4.0

### Changed

- Fixed mypy typing in the codebase [#26](https://github.com/tarsil/saffier/pull/26)
- Updated pyproject.toml requirements [#26](https://github.com/tarsil/saffier/pull/26)

### Added

- UniqueConstraint object for the unique_together [#29](https://github.com/tarsil/saffier/pull/29)
- UniqueConstraint documentation  [#29](https://github.com/tarsil/saffier/pull/29)

## 0.3.0

### Added

- Integrated the support for [native migrations](./migrations/migrations.md) with Saffier.

    * This brings native generated migrations within Saffier under Alembic's package, allowing
a seemless integration and cross-compatibility with any framework using Saffier.

- Added new [DatabaseTestClient](./test-client.md) delegating the creating of the `test` database
for each connection string provided.

    * No more needed to manually create two separate databases thanks to the client that does the
automatic management for you.


## 0.2.1

### Changed

- This was supposed to go in the release 0.2.0 and it was missed. Updated queryset lookup
for functions allowing accesing the model functions from the manager directly.

## 0.2.0

### Added

- New [Index](./models.md#indexes) object allowing the creation of internal SQLAlchemy indexes.

### Changed

- Updated metaclass to validate the fields being added to `indexes`.

## 0.1.0

This is the initial release of Saffier.

* **Model inheritance** - For those cases where you don't want to repeat yourself while maintaining
intregity of the models.
* **Abstract classes** - That's right! Sometimes you simply want a model that holds common fields
that doesn't need to created as a table in the database.
* **Meta classes** - If you are familiar with Django, this is not new to you and Saffier offers this
in the same fashion.
* **Managers** - Versatility at its core, you can have separate managers for your models to optimise
specific queries and querysets at ease.
* **Filters** - Filter by any field you want and need.
* **Model operators** - Classic operations such as `update`, `get`, `get_or_none`, `bulk_create`,
`bulk_update` and a lot more.
* **Relationships made it easy** - Support for `OneToOne` and `ForeignKey` in the same Django style.
* **Constraints** - Unique constraints through meta fields.
