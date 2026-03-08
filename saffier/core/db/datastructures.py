from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass
class Index:
    """Declarative representation of a model-level database index.

    Instances are stored on `Meta.indexes` and later translated into SQLAlchemy
    `Index` objects when a model table is built.
    """

    suffix: str = "idx"
    __max_name_length__: ClassVar[int] = 63
    name: str | None = None
    fields: Sequence[str] | None = None

    def __post_init__(self) -> None:
        if self.name is not None and len(self.name) > self.__max_name_length__:
            raise ValueError(
                f"The max length of the index name must be {self.__max_name_length__}. Got {len(self.name)}"
            )

        if not isinstance(self.fields, (tuple, list)):
            raise ValueError("Index.fields must be a list or a tuple.")

        if self.fields and not all(isinstance(field, str) for field in self.fields):
            raise ValueError("Index.fields must contain only strings with field names.")

        if self.name is None:
            self.name = f"{self.suffix}_{'_'.join(self.fields)}"


@dataclass
class UniqueConstraint:
    """Declarative representation of a multi-field uniqueness constraint.

    Instances are stored on `Meta.unique_together` and expanded into SQLAlchemy
    `UniqueConstraint` objects during table construction.
    """

    fields: list[str]
    name: str | None = None
    __max_name_length__: ClassVar[int] = 63

    def __post_init__(self) -> None:
        if self.name is not None and len(self.name) > self.__max_name_length__:
            raise ValueError(
                f"The max length of the constraint name must be {self.__max_name_length__}. Got {len(self.name)}"
            )

        if not isinstance(self.fields, (tuple, list)):
            raise ValueError("UniqueConstraint.fields must be a list or a tuple.")

        if self.fields and not all(isinstance(field, str) for field in self.fields):
            raise ValueError("UniqueConstraint.fields must contain only strings with field names.")
        self.fields = list(self.fields)


class QueryModelResultCache:
    """Shared queryset result cache keyed by selected model attributes.

    Querysets use this cache to reuse hydrated model instances across repeated
    lookups and relation traversals without forcing a global identity map.
    """

    def __init__(
        self,
        attrs: Sequence[str],
        prefix: str = "",
        cache: dict[str, dict[tuple[Any, ...], Any]] | None = None,
    ) -> None:
        self.attrs = tuple(attrs)
        self.prefix = prefix
        self.cache: dict[str, dict[tuple[Any, ...], Any]] = {} if cache is None else cache

    def create_category(self, model_class: type[Any], prefix: str | None = None) -> str:
        prefix = self.prefix if prefix is None else prefix
        return f"{prefix}_{model_class.__name__}"

    def create_sub_cache(self, attrs: Sequence[str], prefix: str = "") -> "QueryModelResultCache":
        return self.__class__(attrs=attrs, prefix=prefix, cache=self.cache)

    def clear(self, model_class: type[Any] | None = None, prefix: str | None = None) -> None:
        if model_class is None:
            self.cache.clear()
            return

        category = self.create_category(model_class, prefix=prefix)
        cached = self.cache.get(category)
        if cached is not None:
            cached.clear()

    def create_cache_key(
        self,
        model_class: type[Any],
        instance: Any,
        attrs: Sequence[str] | None = None,
        prefix: str | None = None,
    ) -> tuple[Any, ...]:
        key: list[Any] = [self.create_category(model_class, prefix=prefix)]
        attrs = self.attrs if attrs is None else tuple(attrs)

        if isinstance(instance, dict):
            for attr in attrs:
                key.append(str(instance[attr]))
        else:
            for attr in attrs:
                key.append(str(getattr(instance, attr)))
        return tuple(key)

    def get_category(
        self, model_class: type[Any], prefix: str | None = None
    ) -> dict[tuple[Any, ...], Any]:
        return self.cache.setdefault(self.create_category(model_class, prefix=prefix), {})

    def update(
        self,
        model_class: type[Any],
        values: Sequence[Any],
        cache_keys: Sequence[tuple[Any, ...]] | None = None,
        prefix: str | None = None,
    ) -> None:
        if cache_keys is None:
            cache_keys = []
            for instance in values:
                try:
                    cache_key = self.create_cache_key(model_class, instance, prefix=prefix)
                except (AttributeError, KeyError):
                    cache_key = ()
                cache_keys.append(cache_key)

        for cache_key, instance in zip(cache_keys, values, strict=False):
            if len(cache_key) <= 1:
                continue
            self.cache.setdefault(cache_key[0], {})[cache_key] = instance

    def get(
        self,
        model_class: type[Any],
        row_or_model: Any,
        prefix: str | None = None,
    ) -> Any | None:
        try:
            cache_key = self.create_cache_key(model_class, row_or_model, prefix=prefix)
        except (AttributeError, KeyError):
            return None
        return self.cache.get(cache_key[0], {}).get(cache_key)
