# ADR-001 — PostgreSQL driver: psycopg 3

**Status:** Accepted
**Date:** 2026-07-22

## Context

The foundation needs a PostgreSQL driver that supports: async I/O (for the
performance requirement), robust connection pooling, prepared statements,
server-side cursors, COPY, and pipeline mode. It will be isolated behind the
Core `DriverPort`, so this is replaceable — but it is the default we build and
tune against.

## Decision

Use **psycopg 3** (`psycopg[binary,pool]`) as the default driver adapter.

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **psycopg 3** | Native async **and** sync; official `psycopg_pool`; pipeline mode; server-side cursors; COPY; binary protocol; actively maintained; great typing | Slightly newer than psycopg2 | **Chosen** |
| asyncpg | Very fast; async-native | Async-only (we want a sync facade too); different API/type system; no first-party sync path; COPY/pipeline ergonomics differ | Rejected as default |
| psycopg2 | Battle-tested, ubiquitous | No native async; legacy; separate pooling story | Rejected |
| SQLAlchemy Core (as driver) | Nice abstractions | Heavier; we are *lower-level* than SQLAlchemy; would blur the "infra" goal | Rejected |

## Consequences

- **Positive:** one library covers async + sync, pooling, pipelining, COPY, and cursors — matching the performance design in [09](../09-performance.md) without stitching multiple libs.
- **Positive:** the `psycopg_pool.AsyncConnectionPool` gives us the object-pool primitive directly.
- **Negative / mitigation:** if a future benchmark shows asyncpg meaningfully faster for a specific hot path, the `DriverPort` seam lets us add an asyncpg adapter for that data source without touching the core.
- psycopg imports are confined to `_internal/drivers/` (enforced by import-linter).
