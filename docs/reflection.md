# Reflection

When working for a big project, sometimes new, sometimes legacy, you might face cases where there
is already an existing database with tables and views and you simply would like to reflect them
into your code by representation without the need of creating new ones.

This is where Saffier reflection comes in.

## What is reflection

Reflection means the opposite of creating the [models](./models.md), meaning, reading
**tables and views** from an existing back into your code.

Let us see an example.

Imagine you have the following table generated into the database.

```python
{!> ../docs_src/reflection/model.py !}
```

This will create a table called `users` in the database as expected.

!!! Note
    We use the previous example to generate a table for explanation purposes. If you already
    have tables in a given db, you don't need this.

Now you want to reflect the existing table `users` from the database into your models (code).

```python hl_lines="8"
{!> ../docs_src/reflection/reflect.py !}
```

What is happening is:

* The `ReflectModel` is going to the database.
* Reads the existing tables.
* Verifies if there is any `users` table name.
* Converts the `users` fields into Saffier model fields.

### Note

**ReflectModel works with database tables AND database views**. That is right, you can use the
model reflect to reflect existing database tables and database views from any existing database.

## ReflectModel

The reflect model is very similar to `Model` from [models](./models.md) but with a main difference
that won't generate any migrations.

```python
from saffier import ReflectModel
```

The same operations of inserting, deleting, updating and creating are still valid and working
as per normal behaviour.

**Parameters**

As per normal model, it is required the `Meta` class with two parameters.

* **registry** - The [registry](./registry.md) instance for where the model will be generated. This
field is **mandatory** and it will raise an `ImproperlyConfigured` error if no registry is found.

* **tablename** - The name of the table or view to be reflected from the database, **not the class name**.

    <sup>Default: `name of class pluralised`<sup>

Example:

```python hl_lines="13 14"
{!> ../docs_src/reflection/reflect.py !}
```

## Fields

The fields should be declared as per normal [fields](./fields.md) that represents the columns from
the reflected database table or view.

Example:

```python hl_lines="9 10"
{!> ../docs_src/reflection/reflect.py !}
```
