from __future__ import annotations

from typing import Any

from monkay import Monkay

from saffier._instance import Instance
from saffier.conf import _monkay as configured_monkay


def create_monkay(global_dict: dict[str, Any], all_var: list[str]) -> Monkay[Instance, Any]:
    """
    Return Saffier's configured Monkay instance.

    Saffier centralizes Monkay configuration in `saffier.conf._monkay`. This
    helper exists for internal modules that need a factory-shaped entry point
    while still sharing the single configured instance.
    """
    del global_dict, all_var
    return configured_monkay


__all__ = ["Instance", "create_monkay"]
