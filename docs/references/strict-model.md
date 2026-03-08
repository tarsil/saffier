# `StrictModel`

`StrictModel` keeps the same ORM API as `Model`, but tightens runtime behavior.

## What changes compared to `Model`

`StrictModel` adds two important guarantees:

* scalar field assignments are validated immediately
* undeclared public attributes raise `AttributeError`

That makes it a good fit when you want Saffier's ORM without the looser Python
object behavior of the default model class.

## Practical example

```python
class Product(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5, default=1)

    class Meta:
        registry = models


product = Product(name="Tea", rating=5)
product.rating = 6  # raises ValidationError
product.unknown = "value"  # raises AttributeError
```

## What it does not change

`StrictModel` does not change query semantics, registry behavior, relation
loading, or migration output. It is a runtime discipline layer over the normal
Saffier model lifecycle.

::: saffier.StrictModel
    options:
        filters:
        - "!^__dict__"
        - "!^__repr__"
        - "!^__str__"
