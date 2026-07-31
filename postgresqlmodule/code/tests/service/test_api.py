"""Phase 3 — Django service-shell API, OpenAPI, error translation, auth seam."""
from __future__ import annotations

import json

import pytest

from pgfoundation_service import bootstrap, views
from pgfoundation_service.auth import AuthGate, AuthorizationError


def _json(resp):
    return json.loads(resp.content)


async def test_query_endpoint_returns_rows(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/query",
        data={"sql": "SELECT id, total FROM orders", "params": {}},
        content_type="application/json",
    )
    resp = await views.query_view(req, name="orders")
    assert resp.status_code == 200
    body = _json(resp)
    assert body["rows"] == [{"id": 1, "total": "9.90"}]
    assert body["row_count"] == 1
    assert "X-Request-Id" in resp.headers


async def test_execute_endpoint_returns_rowcount(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/execute",
        data={"sql": "UPDATE orders SET x=1", "params": {}},
        content_type="application/json",
    )
    resp = await views.execute_view(req, name="orders")
    assert resp.status_code == 200
    assert _json(resp)["row_count"] == 2


async def test_datasources_and_health(arf, foundation):
    resp = await views.datasources_view(arf.get("/v1/datasources"))
    assert _json(resp)["datasources"] == ["orders"]

    resp = await views.health_view(arf.get("/v1/health"))
    body = _json(resp)
    assert body["status"] == "healthy"
    assert body["datasources"] == {"orders": "healthy"}


async def test_unknown_datasource_maps_to_404(arf, foundation):
    req = arf.post(
        "/v1/datasources/nope/query",
        data={"sql": "SELECT 1", "params": {}},
        content_type="application/json",
    )
    resp = await views.query_view(req, name="nope")
    assert resp.status_code == 404
    assert _json(resp)["type"] == "ConfigError"


async def test_bad_query_maps_to_400(arf, foundation):
    from pgfoundation import ResultSet

    async def boom(name, spec):
        from pgfoundation.core.errors import QueryError
        raise QueryError("42601 syntax error")

    # monkeypatch the facade query for this test
    foundation.query = boom  # type: ignore[method-assign]
    req = arf.post(
        "/v1/datasources/orders/query",
        data={"sql": "SELCT", "params": {}},
        content_type="application/json",
    )
    resp = await views.query_view(req, name="orders")
    assert resp.status_code == 400
    assert _json(resp)["type"] == "QueryError"


async def test_invalid_json_body_maps_to_400(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/query", data="not-json", content_type="application/json"
    )
    resp = await views.query_view(req, name="orders")
    assert resp.status_code == 400


async def test_openapi_spec_is_generated_from_dtos(arf, foundation):
    resp = await views.openapi_view(arf.get("/openapi.json"))
    spec = _json(resp)
    assert spec["openapi"] == "3.0.3"
    for p in ("/v1/datasources/{name}/view", "/v1/datasources/{name}/function",
              "/v1/datasources/{name}/procedure", "/v1/datasources/{name}/query"):
        assert p in spec["paths"]
    for s in ("ViewIn", "FunctionIn", "ProcedureIn", "QueryIn", "QueryOut"):
        assert s in spec["components"]["schemas"]


# --- uniform, name-based invocation endpoints (no raw SQL from the client) ---


async def test_view_endpoint_by_name_with_filters(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/view",
        data={"name": "v_paid_orders", "columns": ["id", "amount"],
              "filters": [{"column": "customer", "op": "eq", "value": "bob"}],
              "order_by": [{"column": "id"}], "limit": 100},
        content_type="application/json",
    )
    resp = await views.view_query_view(req, name="orders")
    assert resp.status_code == 200
    assert _json(resp)["rows"] == [{"id": 1, "total": "9.90"}]  # fake responder


async def test_function_endpoint_by_name(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/function",
        data={"name": "fn_orders_by_customer", "args": {"cust": "bob"}},
        content_type="application/json",
    )
    resp = await views.function_view(req, name="orders")
    assert resp.status_code == 200
    assert _json(resp)["row_count"] == 1


async def test_procedure_endpoint_by_name(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/procedure",
        data={"name": "sp_customer_stats", "args": ["bob", None, None]},
        content_type="application/json",
    )
    resp = await views.procedure_view(req, name="orders")
    assert resp.status_code == 200


async def test_view_endpoint_rejects_bad_operator_with_400(arf, foundation):
    req = arf.post(
        "/v1/datasources/orders/view",
        data={"name": "v", "filters": [{"column": "c", "op": "; DROP", "value": 1}]},
        content_type="application/json",
    )
    resp = await views.view_query_view(req, name="orders")
    assert resp.status_code == 400  # invalid enum op -> validation error


# --- auth seam ---

async def test_auth_disabled_by_default_allows(arf, foundation):
    assert bootstrap.get_auth_gate().enabled is False
    req = arf.post(
        "/v1/datasources/orders/query",
        data={"sql": "SELECT 1", "params": {}},
        content_type="application/json",
    )
    resp = await views.query_view(req, name="orders")
    assert resp.status_code == 200


async def test_auth_enabled_denies_map_to_403(arf, foundation):
    class DenyAuthorizer:
        async def authorize(self, principal, action, resource):
            return False

    class TokenAuthenticator:
        async def authenticate(self, request):
            from pgfoundation_service.auth import Principal
            return Principal(subject="u1")

    bootstrap.set_auth_gate(
        AuthGate(enabled=True, authenticator=TokenAuthenticator(), authorizer=DenyAuthorizer())
    )
    req = arf.post(
        "/v1/datasources/orders/query",
        data={"sql": "SELECT 1", "params": {}},
        content_type="application/json",
    )
    resp = await views.query_view(req, name="orders")
    assert resp.status_code == 403
    assert _json(resp)["type"] == "AuthorizationError"


def test_auth_enabled_without_provider_fails_closed():
    with pytest.raises(RuntimeError, match="refusing to start"):
        AuthGate(enabled=True)
