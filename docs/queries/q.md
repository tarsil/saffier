# Q Expressions

`Q` gives you composable query expressions for complex predicates.

Use it when you need nested boolean logic that is harder to express with chained
`filter()/or_()/not_()` calls.

## Basic Usage

```python
from saffier import Q

query = User.query.filter(Q(name="Adam") & Q(email__icontains="saffier"))
users = await query
```

## OR and NOT

```python
from saffier import Q

# name is Adam OR Saffier
query = User.query.filter(Q(name="Adam") | Q(name="Saffier"))

# NOT name is Adam
query = User.query.filter(~Q(name="Adam"))
```

## Nested Expressions

```python
from saffier import Q

query = User.query.filter((Q(name="Adam") & Q(email__icontains="dev")) | Q(name="Ravyn"))
```

## Related Lookups

`Q` supports the same related lookups used by queryset kwargs.

```python
from saffier import Q

query = Product.query.filter(Q(user__email__icontains="saffier"))
products = await query
```

## Mixing Raw SQLAlchemy Clauses

You can combine `Q` with SQLAlchemy column expressions.

```python
from saffier import Q

query = User.query.filter(Q(User.columns.name == "Adam") & Q(email__icontains="saffier"))
```

## Using `Q` with `or_()`

```python
from saffier import Q

query = User.query.or_(Q(name="Adam")).or_(Q(name="Saffier"))
users = await query
```
