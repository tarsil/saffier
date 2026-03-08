from importlib import import_module

MODULES = [
    "saffier._monkay",
    "saffier.contrib.admin.controllers",
    "saffier.contrib.admin.mixins",
    "saffier.contrib.admin.utils",
    "saffier.contrib.admin.utils.messages",
    "saffier.contrib.admin.utils.models",
    "saffier.contrib.lilya",
    "saffier.contrib.lilya.middleware",
    "saffier.engines",
    "saffier.engines.base",
    "saffier.engines.msgspec",
    "saffier.engines.pydantic",
    "saffier.engines.utils",
    "saffier.core.db.models.mixins.admin",
    "saffier.core.db.models.mixins.db",
    "saffier.core.db.models.mixins.dump",
    "saffier.core.db.models.mixins.reflection",
    "saffier.core.db.models.mixins.row",
    "saffier.core.db.models.types",
    "saffier.core.db.querysets.compiler",
    "saffier.core.db.querysets.executor",
    "saffier.core.db.querysets.mixins.combined",
    "saffier.core.db.querysets.mixins.queryset_props",
    "saffier.core.db.querysets.mixins.tenancy",
    "saffier.core.db.querysets.parser",
    "saffier.core.db.querysets.queryset",
    "saffier.core.db.querysets.types",
    "saffier.core.db.relationships.related_field",
    "saffier.core.tenancy",
    "saffier.core.tenancy.utils",
    "saffier.core.utils.db",
]


def test_edgy_compat_modules_import_cleanly() -> None:
    for module_name in MODULES:
        import_module(module_name)
