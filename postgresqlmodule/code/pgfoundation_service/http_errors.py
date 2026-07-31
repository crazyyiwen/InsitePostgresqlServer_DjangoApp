"""Translate Core + auth errors into HTTP status codes (doc 08 §8.6).

Bodies never leak SQL internals, credentials, or stack traces to the client.
"""
from __future__ import annotations

import uuid

from django.http import HttpResponse, JsonResponse
from pydantic import ValidationError

from pgfoundation import (
    ConfigError,
    ConnectionError as PgConnectionError,
    IntegrityError,
    PgFoundationError,
    PoolTimeoutError,
    QueryError,
    TransientError,
)

from .auth import AuthenticationError, AuthorizationError

# Core error type -> HTTP status
_STATUS = {
    QueryError: 400,
    IntegrityError: 409,
    PoolTimeoutError: 503,
    PgConnectionError: 503,
    TransientError: 503,
    ConfigError: 404,  # unknown data source is a ConfigError
    AuthenticationError: 401,
    AuthorizationError: 403,
}


def status_for(exc: Exception) -> int:
    if isinstance(exc, ValidationError):  # bad/invalid JSON body or schema
        return 400
    for cls, code in _STATUS.items():
        if isinstance(exc, cls):
            return code
    if isinstance(exc, PgFoundationError):
        return 500
    return 500


def error_response(exc: Exception, request_id: str) -> JsonResponse:
    body = {"error": str(exc), "type": type(exc).__name__, "request_id": request_id}
    return JsonResponse(body, status=status_for(exc))


def api(view):
    """Decorator: assign a request-id, translate errors, and JSON-encode."""

    async def wrapper(request, *args, **kwargs):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        try:
            result = await view(request, *args, **kwargs)
            if isinstance(result, HttpResponse):
                result["X-Request-Id"] = request_id
                return result
            resp = JsonResponse(result)
            resp["X-Request-Id"] = request_id
            return resp
        except ValidationError as exc:
            # Don't leak field internals in the summary; keep a clean 400.
            return error_response(QueryError("invalid request body"), request_id)
        except Exception as exc:  # noqa: BLE001 — deliberately translate everything
            return error_response(exc, request_id)

    return wrapper


__all__ = ["api", "error_response", "status_for"]
