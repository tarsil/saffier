# Pagination

Saffier includes Python-native paginators in `saffier.contrib.pagination`:

- `NumberedPaginator` / `Paginator` for page-number navigation.
- `CursorPaginator` for stable cursor-based navigation.

## Numbered pagination

```python
from saffier.contrib.pagination import Paginator

queryset = User.query.order_by("id")
paginator = Paginator(queryset, page_size=25)

page = await paginator.get_page(1)
print(page.current_page, page.next_page, page.previous_page)
```

## Cursor pagination

```python
from saffier.contrib.pagination import CursorPaginator

queryset = User.query.order_by("id")
paginator = CursorPaginator(queryset, page_size=25)

first = await paginator.get_page()
second = await paginator.get_page(first.next_cursor)
back = await paginator.get_page(first.next_cursor, backward=True)
```

## QuerySet helpers

```python
queryset = User.query.order_by("id")

numbered = queryset.paginator(page_size=20)
cursor = queryset.cursor_paginator(page_size=20)
```

Both page objects expose `model_dump()` / `as_dict()` for JSON serialization without Pydantic.
