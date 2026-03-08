# SQLAlchemy Compatibility Mode

Saffier already supports SQLAlchemy-style expressions via `Model.columns.<name>`.

For progressive migrations from legacy SQLAlchemy models, you can opt in to
class-attribute compatibility so `Model.<name>` resolves to SQLAlchemy columns.

## Enable Per Model

```python
import saffier
import sqlalchemy


class Workspace(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


statement = sqlalchemy.select(Workspace.id).where(Workspace.id == 1)
```

## Enable Once On An Abstract Base

If many models need this mode, declare it once on an abstract base model:

```python
class SACompatBase(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    class Meta:
        abstract = True


class Workspace(SACompatBase):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models
```

Concrete subclasses inherit the compatibility behavior automatically.

## What Works

On opted-in concrete models:

```python
sqlalchemy.select(Workspace.id)
sqlalchemy.select(Workspace.id).where(Workspace.id == some_value)
sqlalchemy.select(Workspace.id).order_by(Workspace.id)
```

Foreign keys are exposed as scalar aliases using SQLAlchemy-style names:

```python
# for `owner = saffier.ForeignKey(User, ...)`
Workspace.owner_id
```

## What Does Not Work

Relationship collections and reverse relations are not scalar columns:

* Many-to-many fields such as `Workspace.tags`
* Reverse relationship fields
* `RefForeignKey` helper fields

For these, continue using Saffier's relationship and queryset APIs.

## Compatibility Notes

* This mode is explicit and opt-in only.
* Non-opted-in models keep existing behavior, so `Model.id` still raises `AttributeError`.
* Existing Saffier query patterns keep working, including `Model.columns.<name>`, keyword filters, and `Q`.

## FAQ

### Can I enable this once in an abstract base model?

Yes. All concrete subclasses inherit the compatibility mode. You do not need to
repeat `SQLAlchemyModelMixin` on every child model.

### Does this change normal Saffier query behavior?

No. It only adds SQLAlchemy Core style class-attribute access for opted-in
concrete models.
