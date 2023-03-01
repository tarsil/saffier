# Release Notes

## 0.3.0

### Added

- Integrated the support for [native migrations](./migrations.md) with Saffier.
  
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
