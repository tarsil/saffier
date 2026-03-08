from __future__ import annotations

from base64 import b32encode
from hashlib import blake2b


def hash_to_identifier(key: str | bytes) -> str:
    """
    Build a short deterministic identifier safe for aliases and generated names.
    """
    if isinstance(key, str):
        key = key.encode()
    return f"_{b32encode(blake2b(key, digest_size=16).digest()).decode().rstrip('=')}"


hash_to_identifier_as_string = """
def hash_to_identifier(key: str | bytes) -> str:
    from base64 import b32encode
    from hashlib import blake2b
    if isinstance(key, str):
        key = key.encode()
    return f"_{b32encode(blake2b(key, digest_size=16).digest()).decode().rstrip('=')}"
"""


__all__ = ["hash_to_identifier", "hash_to_identifier_as_string"]
