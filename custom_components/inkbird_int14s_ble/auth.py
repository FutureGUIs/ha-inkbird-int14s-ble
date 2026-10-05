"""Compatibility imports from the forked station library."""

from ._vendor.int14s.auth import (
    build_challenge_request,
    build_clock_sync,
    build_verify_response,
)

__all__ = ["build_challenge_request", "build_verify_response", "build_clock_sync"]
