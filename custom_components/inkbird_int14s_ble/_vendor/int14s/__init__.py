"""Authenticated INT-14S-BW support.

This model has a distinct 54-byte Fahrenheit layout. Do not decode it using
the 18-byte INT-14-BW layout.
"""

import re

from .client import InkbirdConnectionError, INT14SBWClient

__all__ = ["INT14SBWClient", "InkbirdConnectionError", "is_int14s_bw"]


def is_int14s_bw(name: str | None) -> bool:
    """Identify the station by its normalized advertised name."""
    return "int14sbw" in re.sub(r"[^a-z0-9]", "", (name or "").lower())
