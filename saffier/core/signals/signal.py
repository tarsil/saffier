import asyncio
import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from saffier.exceptions import SignalError
from saffier.utils.inspect import func_accepts_kwargs

if TYPE_CHECKING:
    pass


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
        self.receiver_senders: dict[int | tuple[int, int], set[Any] | None] = {}

    def connect(self, receiver: Callable, *, sender: Any | None = None) -> None:
        """Connect one receiver to the signal.

        Args:
            receiver: Callable accepting `**kwargs`.
            sender: Optional sender filter. When provided, the receiver is
                called only when ``send`` uses the same sender value.

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
            self.receiver_senders[key] = set() if sender is not None else None
        if sender is not None and self.receiver_senders[key] is not None:
            self.receiver_senders[key].add(sender)

    def connect_via(self, sender: Any) -> Callable[[Callable], Callable]:
        """Return a decorator that connects a receiver for one sender.

        The method mirrors Blinker's ``connect_via`` ergonomics for migration
        signals while still using Saffier's own dispatcher. It is intentionally
        sender-filtered, which lets one global signal handle ``revision``,
        ``upgrade``, and ``downgrade`` receivers independently.

        Args:
            sender: Sender value that must match future ``send`` calls.

        Returns:
            Callable[[Callable], Callable]: Decorator registering the receiver.
        """

        def wrapper(receiver: Callable) -> Callable:
            self.connect(receiver, sender=sender)
            return receiver

        return wrapper

    def disconnect(self, receiver: Callable) -> bool:
        """Disconnect one receiver from the signal.

        Returns:
            bool: `True` if a receiver was removed.
        """
        key = make_id(receiver)
        func: Callable | None = self.receivers.pop(key, None)
        self.receiver_senders.pop(key, None)
        return func is not None

    async def send(self, sender: Any, **kwargs: Any) -> None:
        """Dispatch the signal to all connected receivers concurrently.

        Args:
            sender: Model class, migration command name, or other sender value
                dispatching the signal.
            **kwargs: Signal payload forwarded to every receiver.
        """
        receivers = []
        for key, func in self.receivers.items():
            allowed_senders = self.receiver_senders.get(key)
            if allowed_senders is not None and sender not in allowed_senders:
                continue
            result = func(sender=sender, **kwargs)
            if inspect.isawaitable(result):
                receivers.append(result)
        if receivers:
            await asyncio.gather(*receivers)


class Broadcaster(dict):
    def __getattr__(self, item: str) -> Signal:
        return self.setdefault(item, Signal())  # type: ignore

    def __setattr__(self, __name: str, __value: Signal) -> None:
        if not isinstance(__value, Signal):
            raise SignalError(f"{__value} is not valid signal")
        self[__name] = __value
