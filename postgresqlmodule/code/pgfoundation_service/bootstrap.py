"""Process-wide holders for the shared DataFoundation + AuthGate.

The shell is *just another consumer* of the framework-free core (doc 08). Wire
these once at startup; tests inject a fake-backed foundation.
"""
from __future__ import annotations

from pgfoundation import DataFoundation

from .auth import AuthGate

_foundation: DataFoundation | None = None
_auth_gate: AuthGate = AuthGate(enabled=False)


def set_foundation(foundation: DataFoundation) -> None:
    global _foundation
    _foundation = foundation


def get_foundation() -> DataFoundation:
    if _foundation is None:
        raise RuntimeError("DataFoundation not initialized — call set_foundation() at startup")
    return _foundation


def set_auth_gate(gate: AuthGate) -> None:
    global _auth_gate
    _auth_gate = gate


def get_auth_gate() -> AuthGate:
    return _auth_gate


async def startup_from_config(path: str) -> DataFoundation:
    """Build + open a foundation from a config file and register it."""
    foundation = await DataFoundation.from_config(path)
    set_foundation(foundation)
    return foundation


__all__ = [
    "set_foundation",
    "get_foundation",
    "set_auth_gate",
    "get_auth_gate",
    "startup_from_config",
]
