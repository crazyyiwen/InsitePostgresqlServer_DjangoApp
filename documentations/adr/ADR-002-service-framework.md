# ADR-002 — Service-shell framework: FastAPI (retire the Django scaffold)

**Status:** **Superseded by [ADR-012](./ADR-012-service-shell-plain-django.md)** (2026-07-24)
**Date:** 2026-07-22

> ⚠️ **Superseded.** This ADR chose FastAPI and recommended retiring the Django
> scaffold. The team knows **plain Django** only and wants OpenAPI, so the shell is
> now **plain Django (ASGI) + apispec + openapi-core** — see
> [ADR-012](./ADR-012-service-shell-plain-django.md). The core stays framework-free
> either way. Content below is retained for history.

## Context

The repository was bootstrapped with a Django `startproject` scaffold
(`postgresqlmodule/code/core`, `manage.py`, SQLite default). The project's real
goal is a **low-level PostgreSQL data foundation** exposed as a library plus a
thin network service. The service shell needs to be async-native (to match
psycopg3 async pools), low-overhead, and give typed schemas — while holding
**no** data-access logic itself.

## Decision

Build the service shell on **FastAPI** (REST) + **grpcio** (optional gRPC), and
**retire the Django scaffold**. The core library remains entirely framework-free.

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **FastAPI + grpcio** | Async-native (matches psycopg3); minimal overhead; Pydantic schemas + OpenAPI for free; great fit for a thin transport skin | New dependency; team may know Django better | **Chosen** |
| Keep Django (DRF / Django-Ninja) | Admin, mature auth, familiarity | Sync-first request path fights async pools; ORM/admin/templating are dead weight for a data foundation; heavier per-request cost | Rejected as default |
| No shell (library only) | Simplest | Fails the "both library + service" decision (ADR-003) | Rejected |

## Consequences

- **Positive:** the shell is a thin async layer over the facade; latency overhead is mostly network + serialization, not framework.
- **Positive:** OpenAPI/proto contracts fall out naturally, enabling the contract tests in [13](../13-testing-strategy.md).
- **Negative / mitigation:** if the organization has a hard Django mandate (reuse of Django admin/auth/existing ops), the shell can be re-skinned as Django-Ninja **without touching the core** — the Facade boundary makes the web framework a swappable detail. This ADR would then be superseded.
- **Action:** the current Django files (`core/settings.py`, `manage.py`, SQLite `DATABASES`) are treated as scaffolding to be replaced by the layout in [12](../12-project-structure-and-packaging.md). No code is removed yet (design-only phase).
