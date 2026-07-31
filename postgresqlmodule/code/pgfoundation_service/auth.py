"""Authentication / authorization seam — DISABLED by default (ADR-013, doc 08 §8.5.1).

The foundation does not implement auth. A separate project registers real
adapters for these ports; the defaults are no-ops (allow all).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AuthError(Exception):
    """Base for auth failures (mapped to 401/403 by the shell)."""


class AuthenticationError(AuthError):
    """401 — could not identify the caller."""


class AuthorizationError(AuthError):
    """403 — caller not permitted for this action/resource."""


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: tuple[str, ...] = ()


class AuthenticatorPort(Protocol):
    async def authenticate(self, request) -> Principal | None: ...


class AuthorizerPort(Protocol):
    async def authorize(self, principal, action: str, resource: str) -> bool: ...


class AllowAllAuthenticator:
    async def authenticate(self, request) -> Principal:
        return Principal(subject="anonymous")


class AllowAllAuthorizer:
    async def authorize(self, principal, action: str, resource: str) -> bool:
        return True


class AuthGate:
    """Runs AuthN then AuthZ when enabled; a pass-through when disabled."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        authenticator: AuthenticatorPort | None = None,
        authorizer: AuthorizerPort | None = None,
    ) -> None:
        self.enabled = enabled
        if enabled and (authenticator is None or authorizer is None):
            # Fail closed: enabled but no provider registered (ADR-013).
            raise RuntimeError(
                "auth.enabled=true but no auth provider registered — refusing to start"
            )
        self._authn = authenticator or AllowAllAuthenticator()
        self._authz = authorizer or AllowAllAuthorizer()

    async def check(self, request, action: str, resource: str) -> Principal:
        if not self.enabled:
            return Principal(subject="anonymous")
        principal = await self._authn.authenticate(request)
        if principal is None:
            raise AuthenticationError("authentication required")
        if not await self._authz.authorize(principal, action, resource):
            raise AuthorizationError(f"not permitted: {action} {resource}")
        return principal


__all__ = [
    "AuthGate",
    "Principal",
    "AuthError",
    "AuthenticationError",
    "AuthorizationError",
    "AuthenticatorPort",
    "AuthorizerPort",
    "AllowAllAuthenticator",
    "AllowAllAuthorizer",
]
