from __future__ import annotations

from typing import Any

from monkay import Monkay

from saffier._instance import Instance
from saffier.conf import _monkay as configured_monkay


def create_monkay(global_dict: dict[str, Any], all_var: list[str]) -> Monkay[Instance, Any]:
    """
    Compatibility helper kept for Edgy-era imports.

    Saffier centralizes Monkay configuration in `saffier.conf._monkay`, so the
    legacy factory simply returns that configured instance.
    """
    del global_dict, all_var
    return configured_monkay


__all__ = ["Instance", "create_monkay"]
