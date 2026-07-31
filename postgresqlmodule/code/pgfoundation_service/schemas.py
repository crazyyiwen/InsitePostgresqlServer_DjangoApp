"""Pydantic DTOs — the source of truth for request/response + OpenAPI (doc 08 §8.3.1)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pgfoundation import FilterOp


class QueryIn(BaseModel):
    """Advanced/trusted: run raw parameterized SQL (prefer the name-based calls)."""

    sql: str = Field(..., description="Parameterized SQL; values go in `params`.")
    params: dict[str, Any] | list[Any] | None = None


# --- Uniform, name-based invocation payloads (the recommended API) ---


class FilterIn(BaseModel):
    column: str
    op: FilterOp = FilterOp.EQ
    value: Any = None


class OrderByIn(BaseModel):
    column: str
    descending: bool = False


class ViewIn(BaseModel):
    """Call a view/table by NAME with structured filters — no SQL."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    db_schema: str | None = Field(default=None, alias="schema")
    columns: list[str] | None = None
    filters: list[FilterIn] = Field(default_factory=list)
    order_by: list[OrderByIn] = Field(default_factory=list)
    limit: int | None = None
    offset: int | None = None


class FunctionIn(BaseModel):
    """Call a function by NAME with args (named mapping or positional list)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    db_schema: str | None = Field(default=None, alias="schema")
    args: dict[str, Any] | list[Any] | None = None
    scalar: bool = False


class ProcedureIn(BaseModel):
    """Call a stored procedure by NAME via CALL (positional args)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    db_schema: str | None = Field(default=None, alias="schema")
    args: list[Any] | None = None


class QueryOut(BaseModel):
    rows: list[dict[str, Any]]
    row_count: int
    elapsed_ms: float


class ExecuteOut(BaseModel):
    row_count: int
    elapsed_ms: float = 0.0


class DataSourceList(BaseModel):
    datasources: list[str]


class HealthOut(BaseModel):
    status: str
    datasources: dict[str, str]


class ErrorOut(BaseModel):
    error: str
    type: str
    request_id: str | None = None


__all__ = [
    "QueryIn",
    "FilterIn",
    "OrderByIn",
    "ViewIn",
    "FunctionIn",
    "ProcedureIn",
    "QueryOut",
    "ExecuteOut",
    "DataSourceList",
    "HealthOut",
    "ErrorOut",
]
