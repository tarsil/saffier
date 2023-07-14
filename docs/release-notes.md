# Release Notes

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
from saffier.db.models import fields
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
