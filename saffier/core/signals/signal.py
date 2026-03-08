import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from saffier.exceptions import SignalError
from saffier.utils.inspect import func_accepts_kwargs

if TYPE_CHECKING:
    from saffier import Model


def make_id(target: Any) -> int | tuple[int, int]:
    """Create a stable identity key for a callable receiver.

    Bound methods are keyed by both instance id and function id so connect and
    disconnect behave predictably across repeated attribute access.
    """
    if hasattr(target, "__func__"):
        return (id(target.__self__), id(target.__func__))
    return id(target)


class Signal:
    """Minimal async signal dispatcher used by model lifecycle hooks.

    Receivers are stored in insertion order and are invoked concurrently when the
    signal is sent.
    """

    def __init__(self) -> None:
        """Initialize an empty receiver registry for the signal."""
        self.receivers: dict[int | tuple[int, int], Callable] = {}

    def connect(self, receiver: Callable) -> None:
        """Connect one receiver to the signal.

        Args:
            receiver: Callable accepting `**kwargs`.

        Raises:
            SignalError: If the receiver is not callable or does not accept
                keyword arguments.
        """
        if not callable(receiver):
            raise SignalError("The signals should be callables")

        if not func_accepts_kwargs(receiver):
            raise SignalError("Signal receivers must accept keyword arguments (**kwargs).")

        key = make_id(receiver)
        if key not in self.receivers:
            self.receivers[key] = receiver

    def disconnect(self, receiver: Callable) -> bool:
        """Disconnect one receiver from the signal.

        Returns:
            bool: `True` if a receiver was removed.
        """
        key = make_id(receiver)
        func: Callable | None = self.receivers.pop(key, None)
        return func is not None

    async def send(self, sender: type["Model"], **kwargs: Any) -> None:
        """Dispatch the signal to all connected receivers concurrently.

        Args:
            sender: Model class sending the signal.
            **kwargs: Signal payload forwarded to every receiver.
        """
        receivers = [func(sender=sender, **kwargs) for func in self.receivers.values()]
        await asyncio.gather(*receivers)


class Broadcaster(dict):
    def __getattr__(self, item: str) -> Signal:
        return self.setdefault(item, Signal())  # type: ignore

    def __setattr__(self, __name: str, __value: Signal) -> None:
        if not isinstance(__value, Signal):
            raise SignalError(f"{__value} is not valid signal")
        self[__name] = __value
