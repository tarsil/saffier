# Models

Have you ever wondered how time consuming and sometimes how hard is to declare a simple table
with SQL Alchemy where sometimes it can also be combersome?

What about the Django interface type for tables? Cleaner right? Well, **Saffier** although is on
the top of SQL Alchemy core, it provides a Django like experience when it comes to create models.

## What is a model

A model in Saffier is python class with attributes that represents a database table behind the
scenes.

In other words, it is what represents your table in your codebase.

## Declaring models

When declaring models by simply inheriting from `saffier.Model` object and define the attributes
using the saffier [Fields](./fields.md).

For each model defined you also need to set **one** mandatory field, the `registry` which is also
an instance of `Registry` from Saffier.

There are more parameters you can use and pass into the model such as [tablename](#metaclass) and
a few more but more on this in this document.

Since **Saffier** took inspiration from the interface of Django, that also means that a `Meta`
class should be declare.

```python
{!> ../docs_src/models/declaring_models.py !}
```

Although this looks very simple, in fact **Saffier** is doing a lot of work for you behind the
scenes.