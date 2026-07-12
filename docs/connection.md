# Connection

Using Saffier is extremely simple and easy to do, but there are some steps you might want to take
into consideration around connections and what can happen if this is not done properly.

Saffier runs directly on SQLAlchemy 2.x Async, using `AsyncEngine` and `AsyncConnection`
under the ORM APIs. What happens if you want to use it within your favourite frameworks like
[Ravyn](https://ravyn.dymmond.com),
Starlette or even FastAPI?

Well, Saffier is framework agnostic so it will fit in any framework you want, even in those that
are not listed above that support **lifecycle events**.

## Lifecycle events

These are very common amongst those frameworks that are based on Starlette, like
[Ravyn](https://ravyn.dymmond.com) or FastAPI but other might have a similar approach but
using different approaches.

The common lifecycle events are the following:

* **on_startup**
* **on_shutdown**
* **lifespan**

This document will focus on the two more commonly used, `on_startup` and `on_shutdown`.

## Hooking your database connection into your application

Hooking a connection is as easy as putting them inside those events in your framework.

For this example, since the author is the same as the one of [Ravyn](https://ravyn.dymmond.com),
we will be using it for explanatory purposes, feel free to apply the same principle in your favourite
framework.

```python
{!> ../docs_src/connections/simple.py !}
```

And that is pretty much this. Once the connection is hooked into your application lifecycle you
will have a live SQLAlchemy async engine available for ORM operations.

You are now free to use the ORM anywhere in your application.

## Note

Check the [tips and tricks](./tips-and-tricks.md) and learn how to make your connections even cleaner.
