from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from saffier import Model


class Send:
    """Decorator factory namespace for model lifecycle signal helpers.

    The class keeps the individual `pre_*` and `post_*` decorators thin while
    centralizing the logic that binds one receiver function to one or more
    model signal broadcasters.
    """

    def consumer(signal: str, senders: type["Model"] | list[type["Model"]]) -> Callable:
        """Create a decorator that connects a receiver to one signal on many senders.

        Args:
            signal: Signal name on the model broadcaster.
            senders: One model or a list of models to bind.

        Returns:
            Callable: Decorator that registers the wrapped function.
        """

        def wrapper(func: Callable) -> Callable:
            _senders = [senders] if not isinstance(senders, list) else senders

            for sender in _senders:
                signals = getattr(sender.meta.signals, signal)
                signals.connect(func)
            return func

        return wrapper


def pre_save(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `pre_save`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `pre_save` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="pre_save", senders=senders)


def pre_update(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `pre_update`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `pre_update` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="pre_update", senders=senders)


def pre_delete(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `pre_delete`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `pre_delete` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="pre_delete", senders=senders)


def post_save(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `post_save`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `post_save` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="post_save", senders=senders)


def post_update(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `post_update`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `post_update` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="post_update", senders=senders)


def post_delete(senders: type["Model"] | list[type["Model"]]) -> Callable:
    """Return a decorator that subscribes a receiver to `post_delete`.

    Args:
        senders (type[Model] | list[type[Model]]): Model class or classes whose
            `post_delete` signal should be observed.

    Returns:
        Callable: Decorator registering the wrapped receiver.
    """
    return Send.consumer(signal="post_delete", senders=senders)
