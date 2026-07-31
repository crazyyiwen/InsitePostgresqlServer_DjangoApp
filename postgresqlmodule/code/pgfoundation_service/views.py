"""Async Django views — a thin transport skin over the L3 Facade (doc 08).

No data-access logic lives here: validate (Pydantic) -> call the Facade ->
serialize. Auth is checked via the pluggable gate (disabled by default).
"""
from __future__ import annotations

from django.http import HttpResponse, JsonResponse

from pgfoundation import (
    Command,
    Filter,
    FunctionQuery,
    OrderBy,
    ProcedureCall,
    Query,
    ViewQuery,
)

from .bootstrap import get_auth_gate, get_foundation
from .http_errors import api
from .openapi import build_spec
from .schemas import (
    DataSourceList,
    ExecuteOut,
    FunctionIn,
    HealthOut,
    ProcedureIn,
    QueryIn,
    QueryOut,
    ViewIn,
)


def _result(rs) -> dict:
    return QueryOut(rows=rs.rows, row_count=rs.rowcount, elapsed_ms=rs.elapsed_ms).model_dump()


# --- Recommended: governed, name-based invocation (no raw SQL from clients) ---


@api
async def view_query_view(request, name: str):
    """POST a view NAME + structured filters; compiled to safe SQL server-side."""
    await get_auth_gate().check(request, action="read", resource=name)
    dto = ViewIn.model_validate_json(request.body)
    spec = ViewQuery(
        name=dto.name,
        schema=dto.db_schema,
        columns=dto.columns,
        filters=tuple(Filter(f.column, f.op, f.value) for f in dto.filters),
        order_by=tuple(OrderBy(o.column, o.descending) for o in dto.order_by),
        limit=dto.limit,
        offset=dto.offset,
    )
    return _result(await get_foundation().view(name, spec))


@api
async def function_view(request, name: str):
    """POST a function NAME + args (named mapping or positional list)."""
    await get_auth_gate().check(request, action="read", resource=name)
    dto = FunctionIn.model_validate_json(request.body)
    spec = FunctionQuery(
        name=dto.name, args=dto.args, schema=dto.db_schema, scalar=dto.scalar
    )
    return _result(await get_foundation().function(name, spec))


@api
async def procedure_view(request, name: str):
    """POST a procedure NAME + positional args; CALLed server-side."""
    await get_auth_gate().check(request, action="write", resource=name)
    dto = ProcedureIn.model_validate_json(request.body)
    spec = ProcedureCall(name=dto.name, args=dto.args, schema=dto.db_schema)
    return _result(await get_foundation().procedure(name, spec))


# --- Advanced/trusted: raw parameterized SQL (kept for internal tooling) ---


@api
async def query_view(request, name: str):
    await get_auth_gate().check(request, action="read", resource=name)
    dto = QueryIn.model_validate_json(request.body)
    return _result(await get_foundation().query(name, Query(dto.sql, dto.params)))


@api
async def execute_view(request, name: str):
    await get_auth_gate().check(request, action="write", resource=name)
    dto = QueryIn.model_validate_json(request.body)
    n = await get_foundation().execute(name, Command(dto.sql, dto.params))
    return ExecuteOut(row_count=n).model_dump()


@api
async def datasources_view(request):
    await get_auth_gate().check(request, action="list", resource="*")
    return DataSourceList(datasources=get_foundation().names()).model_dump()


@api
async def health_view(request):
    health = await get_foundation().health()
    per = {name: status.value for name, status in health.items()}
    overall = "healthy" if all(v == "healthy" for v in per.values()) else "degraded"
    return HealthOut(status=overall, datasources=per).model_dump()


async def openapi_view(request):
    return JsonResponse(build_spec())


async def docs_view(request):
    html = """<!doctype html><html><head><title>pgfoundation-service — API</title></head>
<body><h1>pgfoundation-service</h1>
<p>OpenAPI spec: <a href="/openapi.json">/openapi.json</a></p>
<p>Vendor Swagger UI static assets here and point them at /openapi.json (doc 08 §8.3.1).</p>
</body></html>"""
    return HttpResponse(html, content_type="text/html")


__all__ = [
    "view_query_view",
    "function_view",
    "procedure_view",
    "query_view",
    "execute_view",
    "datasources_view",
    "health_view",
    "openapi_view",
    "docs_view",
]
