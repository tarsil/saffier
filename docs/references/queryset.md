# `QuerySet`

`QuerySet` is Saffier's lazy query builder and execution API.

Managers return querysets, queryset methods clone and refine query state, and
terminal operations such as `get()`, `all()`, `create()`, `update()`, and
`delete()` finally touch the database.

## Mental model

Think of a queryset as an immutable query plan:

* `filter()` and `exclude()` add predicates
* `select_related()` changes how related rows are joined and hydrated
* `only()` and `defer()` change projection
* `order_by()`, `limit()`, and `offset()` shape the final result set
* terminal methods execute the plan

## Practical example

```python
recent_users = (
    User.query
    .filter(is_active=True, email__icontains="@example.com")
    .select_related("team")
    .order_by("-created_at")
    .limit(20)
)

rows = await recent_users.all()
```

## Performance notes

Use `select_related()` for foreign-key joins you know you will dereference.

Use `prefetch_related()` for collections or fan-out paths where one giant join
would duplicate too many rows.

Use `only()` or `defer()` when you want to reduce transfer size but still keep
model instances.

::: saffier.QuerySet
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__await__"
        - "!^__class_getitem__"
        - "!^__get__"
        - "!^ESCAPE_CHARACTERS"
        - "!^m2m_related"
        - "!^pkname"
        - "!^_m2m_related"
