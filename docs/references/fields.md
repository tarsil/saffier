# `Field`

All Saffier model fields inherit from `Field`.

The base class is where Saffier joins together three different concerns:

* validation through an internal validator object
* SQLAlchemy column generation
* ORM-side normalization such as composite-field expansion or relation cleanup

## Common options shared by most fields

The exact supported arguments vary by field type, but the base field behavior
is where options such as these are enforced:

* `primary_key`
* `null`
* `default`
* `server_default`
* `index`
* `unique`
* `column_name`
* `exclude`
* `secret`

## Why the base field matters

When you define a custom field or debug an unexpected write behavior, the base
field API is the contract to understand:

* `clean()` converts a logical field value into one or more database columns
* `modify_input()` can expand or rewrite incoming payloads
* `get_global_constraints()` can add foreign keys or indexes to the table
* `pre_save_callback()` can generate write-time values before persistence

::: saffier.core.db.fields.base.Field
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
