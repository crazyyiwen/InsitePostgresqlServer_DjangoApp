"""Code-first OpenAPI 3 from the Pydantic DTOs, via apispec (doc 08 §8.3.1).

The spec stays in sync with the DTOs by construction — no hand-maintained YAML.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from apispec import APISpec

from . import schemas


@lru_cache(maxsize=1)
def build_spec() -> dict[str, Any]:
    spec = APISpec(
        title="pgfoundation-service",
        version="1.0.0",
        openapi_version="3.0.3",
        info={"description": "PostgreSQL Database Foundation Server — REST API"},
    )

    # Register component schemas straight from the Pydantic models.
    for name in (
        "ViewIn", "FunctionIn", "ProcedureIn", "QueryIn",
        "QueryOut", "ExecuteOut", "DataSourceList", "HealthOut", "ErrorOut",
    ):
        model = getattr(schemas, name)
        # inline nested $defs (FilterIn/OrderByIn) so the spec is self-contained
        spec.components.schema(name, model.model_json_schema(ref_template="#/components/schemas/{model}"))

    _ref = lambda n: {"$ref": f"#/components/schemas/{n}"}  # noqa: E731
    err = {"application/json": {"schema": _ref("ErrorOut")}}

    def _op(summary, body=None, ok="QueryOut"):
        op: dict[str, Any] = {
            "summary": summary,
            "responses": {
                "200": {"description": "OK", "content": {"application/json": {"schema": _ref(ok)}}},
                "4XX": {"description": "client error", "content": err},
                "503": {"description": "unavailable", "content": err},
            },
        }
        if body:
            op["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": _ref(body)}},
            }
        return op

    name_param = [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}]

    def _post(summary, body, ok, tag):
        return {"post": {**_op(summary, body, ok), "parameters": name_param, "tags": [tag]}}

    # Recommended: governed, name-based invocation.
    spec.path("/v1/datasources/{name}/view",
              operations=_post("Query a view/table by name", "ViewIn", "QueryOut", "invoke"))
    spec.path("/v1/datasources/{name}/function",
              operations=_post("Call a function by name", "FunctionIn", "QueryOut", "invoke"))
    spec.path("/v1/datasources/{name}/procedure",
              operations=_post("Call a stored procedure by name", "ProcedureIn", "QueryOut", "invoke"))
    # Advanced/trusted: raw SQL.
    spec.path("/v1/datasources/{name}/query",
              operations=_post("Run a read query (raw SQL — advanced)", "QueryIn", "QueryOut", "advanced"))
    spec.path("/v1/datasources/{name}/execute",
              operations=_post("Run a write command (raw SQL — advanced)", "QueryIn", "ExecuteOut", "advanced"))
    # Admin.
    spec.path("/v1/datasources", operations={"get": _op("List data sources", None, "DataSourceList")})
    spec.path("/v1/health", operations={"get": _op("Health / readiness", None, "HealthOut")})
    return spec.to_dict()


__all__ = ["build_spec"]
