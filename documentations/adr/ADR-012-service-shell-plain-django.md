# ADR-012 — Service shell: plain Django (ASGI) + apispec + openapi-core

**Status:** Accepted — **supersedes [ADR-002](./ADR-002-service-framework.md)**
**Date:** 2026-07-24

## Context

[ADR-002](./ADR-002-service-framework.md) chose **FastAPI** for the service shell,
noting a Django-Ninja/DRF fallback if the team had a hard Django requirement. The
team's actual constraint is now explicit:

> The team knows **plain Django** only, and wants the **OpenAPI** feature
> (interactive docs, client generation, contract enforcement).

Team fluency is a decisive, legitimate architectural factor. Because the design
already isolates *all* data-access logic in the **framework-free core library**
([ADR-003](./ADR-003-library-and-service.md)), the web framework is a swappable L4
detail — so we can adopt Django with no impact on the foundation.

Plain Django has **no built-in OpenAPI generator** (that is a DRF/Ninja feature),
so the shell must add a small, framework-agnostic OpenAPI toolchain.

## Decision

Build the service shell on **plain Django on ASGI, with async views**, plus a
Pydantic-driven OpenAPI toolchain — **no FastAPI, no DRF, no Django Ninja**:

| Concern | Choice |
|---------|--------|
| Web framework | **plain Django** (ASGI); **`async def` views** that `await` the async Facade |
| Request/response schemas | **Pydantic v2** DTOs (reused from the foundation) |
| OpenAPI document | **`apispec`** — assembles the OpenAPI 3 spec **code-first** from the Pydantic schemas |
| Contract enforcement | **`openapi-core`** (`openapi_core.contrib.django`) — validate requests/responses against the spec, in tests and (optionally) dev middleware |
| Interactive docs | **Swagger UI / ReDoc**, vendored static assets, pointed at `/openapi.json` (no CDN) |
| gRPC (optional) | **`grpcio`** server, run alongside — independent of the web framework |

Approach is **code-first**: DTOs are the source of truth; the spec is generated
from them, so it cannot silently drift. A ~40-line helper registers each route's
`(path, method, request_model, response_model)` into `apispec` so operation blocks
aren't hand-written.

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Plain Django + apispec + openapi-core (chosen)** | Team's exact framework; async-capable; OpenAPI + contract enforcement; framework-free core untouched | More wiring than Ninja; "auto" becomes "generate-from-Pydantic + validate" | **Chosen (team constraint)** |
| FastAPI (ADR-002) | Async-native, auto OpenAPI free | Team doesn't know it | Superseded |
| Django Ninja | Auto OpenAPI free, Django-based | A different API style than plain Django; extra dependency the team didn't ask for | Rejected (team wants *plain* Django) |
| DRF + drf-spectacular | Mature, familiar to many Django teams | Sync-first (fights async pools); heavier; not "plain Django" | Rejected |

## Consequences

- **Positive:** the team builds the shell in the framework they know; OpenAPI docs, client generation, and contract tests ([13](../13-testing-strategy.md)) are all available.
- **Positive:** reconciles with the repo's existing Django scaffold (`postgresqlmodule/code`) — it can be **repurposed as the shell** rather than retired. (ADR-002 recommended retiring it; that reversal is the point of this ADR.)
- **Positive:** the **core library remains framework-free** and uses **no ORM** — Django is used only as the L4 HTTP layer (its ORM/migrations are not used for foundation data access, and the foundation owns no tables). Django **admin** may optionally be kept for ops.
- **Negative / mitigation:** more manual than a framework with built-in OpenAPI — mitigated by the code-first Pydantic→apispec generator and `openapi-core` contract tests that fail CI on drift.
- **Async note:** the shell uses ASGI `async def` views awaiting the async Facade; a sync-façade wrapper remains available for any sync view that needs it.
- **Import-linter:** `pgfoundation_service` may import Django; the **core `pgfoundation` package must not** — the existing contract that forbids web frameworks in the core still holds.
