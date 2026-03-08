# `ReflectModel`

`ReflectModel` is the base class for models backed by existing database tables
or views.

Use it when the schema already exists and you want Saffier to inspect the
database rather than generate the table definition from declared fields.

## What is different from `Model`

* the SQLAlchemy table is reflected from the database
* reflection uses the synchronous SQLAlchemy engine internally
* the model is stored in `registry.reflected` instead of the normal
  `registry.models` mapping

## Practical use

`ReflectModel` is most useful for:

* legacy databases
* reporting or analytics tables maintained elsewhere
* read-heavy integrations where the table shape is not owned by the Saffier app

When mixing reflected and declared models in the same registry, relations and
querysets still resolve against both sources.

::: saffier.ReflectModel
    options:
        filters:
        - "!^model_config"
        - "!^__dict__"
        - "!^__repr__"
        - "!^__str__"
