# Reference ForeignKey

`RefForeignKey` has two complementary modes in Saffier:

1. A regular foreign key with extra reference metadata via `ref_field`.
2. A Python-native nested-insert helper when you point it at a `ModelRef`.

## ModelRef-backed inserts

Use `ModelRef` when you want to create a parent model and stage related child rows in the same call,
without pulling Pydantic into Saffier.

```python
import saffier


class PostRef(saffier.ModelRef):
    __related_name__ = "posts_set"
    comment: str


class Post(saffier.StrictModel):
    user = saffier.ForeignKey("User", on_delete=saffier.CASCADE)
    comment = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100, null=True)
    posts = saffier.RefForeignKey(PostRef, null=True)

    class Meta:
        registry = models
```

Then create related rows inline:

```python
await User.query.create(
    PostRef(comment="first"),
    PostRef(comment="second"),
    name="Edgy-compatible",
    posts=[],
)
```

You can also pass dictionaries:

```python
await User.query.create(name="Inline", posts=[{"comment": "from a dict"}])
```

`RefForeignKey(ModelRef)` is a virtual field. It does not create a database column. Instead, it
uses the `ModelRef.__related_name__` relation to create the concrete related rows after the parent
instance has been saved.

## Classic reference metadata

If you point `RefForeignKey` at a real Saffier model, it keeps the existing Saffier behavior and
acts like a normal foreign key with an extra `ref_field` hint:

```python
class Team(saffier.Model):
    slug = saffier.CharField(max_length=120, unique=True)


class Member(saffier.Model):
    team = saffier.RefForeignKey(Team, ref_field="slug", on_delete=saffier.CASCADE)
```

This keeps existing Saffier projects compatible while adding the richer Edgy-style reference flow.
