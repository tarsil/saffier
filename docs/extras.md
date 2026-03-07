# Extras

This section refers to the extras that Saffier offer and can be used in your application without
incurring into extra overhead to make it happen.

If you are in this section, you surely read about the [auto discovery](./migrations/discovery.md)
and how it relates with the way Saffier handles and manages migrations for you.

But, what if you simply would like to use the [shell](./shell.md) or any related command offered
by Saffier that does not require migration management?

The current runtime entry point is `saffier.Instance(...)` plus
`saffier.monkay.set_instance(...)`. The deprecated `Migrate(...)` wrapper still
exists for compatibility, but it is no longer the preferred bootstrap. There
are also cases where migration management is not needed at all, for example a
project using [reflect models](./reflection.md).

A project using reflect models means migrations are managed externally and
Saffier only needs to reflect those tables back into your code, so the answer is
still no.

So how can you still use those features without coupling your setup to the
compatibility wrapper? Use [SaffierExtra](#saffierextra).

## SaffierExtra

This is the object you want to use when you do not need Saffier to manage
migrations and still want Saffier tooling such as the [shell](./shell.md).

### How does it work

It follows the same active-instance runtime direction as the rest of the
current Saffier bootstrap.

Let us use [Ravyn](https://ravyn.dymmond.com) again as an example like we did for the
[tips and tricks](./tips-and-tricks.md).

```python hl_lines="12 47"
{!> ../docs_src/extras/app.py !}
```

And that is it, you can use any tool that does not relate with migrations in your application.

!!! Warning
    Be aware of the use of this special class in production! It is advised not to use it there.

## Note

For now, besides the migrations and the shell, Saffier does not offer any extra tools but there are
plans to add more extras in the future and `SaffierExtra` is the way to go for that setup.
