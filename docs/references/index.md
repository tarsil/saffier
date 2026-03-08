# API Reference

The pages in this section are the API-first companion to the guide pages.

Use the guides when you want a narrative walkthrough, migration strategy, or
end-to-end example. Use the reference pages when you already know the concept
you need and want to confirm the exact runtime behavior, public surface, and
important constraints.

## How to read the reference

Most Saffier features are layered:

* models declare fields and managers
* managers hand out querysets
* querysets build SQLAlchemy expressions
* registries own databases, metadata, and model registration
* relation fields bind reverse descriptors and through models

That means one feature is usually documented across more than one page. A
common navigation path looks like this:

1. Read [Model](./models.md) for instance lifecycle and persistence behavior.
2. Read [Field](./fields.md) plus the specific relation page for declaration
   details.
3. Read [QuerySet](./queryset.md) or [Manager](./manager.md) for querying.
4. Read [Registry](./registry.md) and [Database](./database.md) for runtime
   setup and migration preparation.

## Suggested starting points

If you are building a new application, start with:

* [Model](./models.md)
* [Field](./fields.md)
* [ForeignKey](./foreignkey.md)
* [QuerySet](./queryset.md)
* [Registry](./registry.md)

If you are integrating Saffier into an existing database or framework, start
with:

* [ReflectModel](./reflect-model.md)
* [Database](./database.md)
* [Registry](./registry.md)
