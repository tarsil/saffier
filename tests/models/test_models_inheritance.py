from typing import ClassVar

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def build_registry() -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL))


def test_direct_descendant() -> None:
    registry_obj = build_registry()

    class Cat(saffier.StrictModel):
        class Meta:
            registry = registry_obj

        objects: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    Cat.proxy_model  # noqa: B018
    Cat.copy_edgy_model().proxy_model  # noqa: B018


def test_second_manager() -> None:
    registry_obj = build_registry()

    class DjangoBase(saffier.StrictModel):
        class Meta:
            abstract = True

        objects: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    class Cat(DjangoBase):
        class Meta:
            registry = registry_obj

        objects: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    class Cat2(Cat, DjangoBase):
        class Meta:
            registry = registry_obj

        objects2: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    Cat.proxy_model  # noqa: B018
    Cat.copy_edgy_model().proxy_model  # noqa: B018
    Cat2.proxy_model  # noqa: B018
    Cat2.copy_edgy_model().proxy_model  # noqa: B018
    DjangoBase.proxy_model  # noqa: B018
    DjangoBase.copy_edgy_model().proxy_model  # noqa: B018


def test_abstract_registry() -> None:
    registry_obj = build_registry()

    class DjangoBase(saffier.StrictModel):
        class Meta:
            abstract = True
            registry = registry_obj

        objects: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    class Cat(DjangoBase):
        objects: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    class Cat2(Cat, DjangoBase):
        objects2: ClassVar[saffier.Manager] = saffier.RedirectManager(redirect_name="query")

    assert "DjangoBase" not in registry_obj.models
    assert "Cat" in registry_obj.models
    assert "Cat2" in registry_obj.models

    Cat.proxy_model  # noqa: B018
    Cat.copy_edgy_model().proxy_model  # noqa: B018
    Cat2.proxy_model  # noqa: B018
    Cat2.copy_edgy_model().proxy_model  # noqa: B018
    DjangoBase.proxy_model  # noqa: B018
    DjangoBase.copy_edgy_model().proxy_model  # noqa: B018
