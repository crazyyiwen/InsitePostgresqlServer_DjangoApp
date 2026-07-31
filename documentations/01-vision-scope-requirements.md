# 01 — Vision, Scope & Requirements

## 1.1 Vision

Build a **PostgreSQL Database Foundation Server**: a hardened, reusable
*infrastructure layer* that every downstream application in the organization
uses to talk to PostgreSQL — instead of each project re-implementing connection
handling, pooling, retries, transactions, and configuration.

It is a **foundation**, not an application. It has no business logic of its own.
Its value is that it makes correct, fast, observable, secure PostgreSQL access
*the path of least resistance* for the teams that depend on it.

> Think of it as the equivalent of a JDBC/HikariCP + Spring-Data foundation, but
> for the Python/PostgreSQL world, delivered both as a library and as a service.

## 1.2 Problem statement

Today, without this foundation, every project independently:

- opens raw connections and leaks them under load;
- hard-codes DSNs, credentials, and pool sizes;
- reinvents retry/timeout/transaction handling inconsistently;
- has no shared observability (slow-query logs, pool metrics);
- cannot easily talk to *more than one* PostgreSQL database in a disciplined way.

This causes outages (pool exhaustion), security incidents (credentials in code),
and duplicated, divergent effort.

## 1.3 Goals (in-scope)

| ID | Goal |
|----|------|
| G1 | Manage **N named PostgreSQL data sources** from one process, each independently pooled and configured. |
| G2 | Expose a **curated set of reusable, composable *basic* APIs** (read, write, transaction, streaming, interval, bulk/batch, admin) — typed and stable — while hiding all internals. Not a single monolithic call; not raw psycopg. See [11 §11.4a](./11-public-api-reference.md). |
| G3 | Guarantee **zero hard-coded** operational values — every value is externally configurable. |
| G4 | Deliver **best-in-class performance**: async pooling, prepared statements, pipelining, COPY-based bulk paths. |
| G5 | Be **clearly layered and decoupled** via ports & adapters, so any piece is replaceable/testable in isolation. |
| G6 | Ship as **both** an installable library and a network service — same core, two skins. |
| G7 | Provide first-class **observability, security, and resilience** as cross-cutting concerns. |
| G8 | Remain **extensible** so future capabilities build on the foundation via ports/dependency, not a rewrite. |
| G9 | **Support** (via clean, generic seams) a future dynamic semantic layer — the foundation enables it without implementing it. |

### 1.3.1 Added requirements (2026-07) — the semantic layer

Following the Insite API design update, three requirements are added. The
**semantic layer itself will be designed later** (a separate, higher-level
concern, deferred). The foundation's job now is only to **support** it via clean,
generic seams (composable `QuerySpec` + safe parameterization, materialized-view
lifecycle, an access-filter hook) so that future work needs no core change.

| ID | Requirement | Owned by |
|----|-------------|----------|
| N1 | Between the database layer and the UI layer, support a **dynamic semantic layer** that **reduces hand-coding** and enables **dynamic search based on user requirements**. | *deferred — design later* |
| N2 | The database server must **account for the semantic-layer case**: **no hard-coded code**, proper **design patterns**, **clean-code** organization — i.e. expose the clean *seams* a semantic layer needs. | **foundation** |
| N3 | Enable **flexible development** as new requirements arrive (change higher-level metadata/models, not the stable DB contract). | *deferred — design later* |
| N4 | The database server must support **streaming** (large/continuous reads, streaming ingest, streaming delivery) and **interval data fetching** (time-bucketed/windowed queries + resumable incremental pulls). Designed in [16 — Streaming & Interval Fetching](./16-streaming-and-interval-fetching.md). | foundation |
| N5 | The service API must **support AuthN/AuthZ as a pluggable seam** for future use — **disabled by default now**, with the real implementation **integrated from a separate project**. The foundation provides the seam, not the auth. See [08 §8.5.1](./08-service-shell.md), [ADR-013](./adr/ADR-013-auth-pluggable-seam.md). | foundation (seam only) |
| N6 | **Observability (logs, metrics, traces) is integrated from a separate log/observability project — not built from scratch here.** The foundation instruments its code through ports and binds to the external pipeline; default is no-op. See [10 §10.1](./10-observability-security-resilience.md), [ADR-014](./adr/ADR-014-observability-external-integration.md). | foundation (instrument + integrate) |

## 1.4 Non-goals (out-of-scope, at least for v1)

- **Not an ORM, and not a schema owner.** We are lower-level than Django ORM / SQLAlchemy ORM. There are **no ORM models** in the foundation, and the foundation **owns no database tables and performs no schema initialization** — every table is defined and created by the consuming project (plain SQL, Flyway, sqitch, or its own ORM/migrations; the foundation imposes none and ships none). We *may* interoperate with a consumer's ORM, but the foundation itself neither defines nor creates tables. See [12 §12.9](./12-project-structure-and-packaging.md).
- **Not a business-domain service.** No domain entities, no CRUD-for-a-specific-app.
- **The semantic layer is not built here — it will be designed later.** The foundation only exposes generic seams (composable `QuerySpec`, materialized-view lifecycle, access-filter hook). The Registry/Compiler/Policy/Aggregate-Planner/Serving are a deferred, higher-level concern.
- **Not a multi-engine abstraction** — PostgreSQL only. We will *not* add MySQL/MS SQL. (The dialect seam exists, but PostgreSQL is the sole target.)
- **Time-series is out of scope — to be designed later.** TimescaleDB / time-series (hypertables, continuous aggregates, retention) is deferred. The foundation only keeps clean, generic seams (a pluggable interval-bucketing Strategy shipping the generic PostgreSQL implementation, `DriverPort`) so a future time-series project can plug in.
- **Vector / NL semantic search** belongs to the (deferred) semantic layer — not built here.
- **API authentication & authorization are not implemented here.** The foundation exposes a **pluggable auth seam, disabled by default**; the real AuthN/AuthZ is **integrated from a separate project** ([08 §8.5.1](./08-service-shell.md), [ADR-013](./adr/ADR-013-auth-pluggable-seam.md)). Until then the service runs open on a trusted network.
- **Observability is not implemented from scratch.** No home-grown logging/metrics/tracing pipeline — the foundation only **instruments** through ports and **integrates** a separate log/observability project (which owns exporters, collectors, dashboards, log storage). Default is no-op. See [10 §10.1](./10-observability-security-resilience.md), [ADR-014](./adr/ADR-014-observability-external-integration.md).
- **Change-data-capture / logical-replication ingest** is **seam-only** in v1 — `LISTEN/NOTIFY` and streaming `COPY` are in scope; CDC is a reserved port. See [16 §16.6](./16-streaming-and-interval-fetching.md).
- **Not a stream-processing engine.** We stream data in/out of PostgreSQL; we do not replace Kafka/Flink-style processing (we integrate with it).
- **Not a schema-migration tool and not a schema owner.** The foundation ships **no `schema/` DDL, no migration runner, and owns no tables** — all schema is defined and created by the consuming project with whatever tool it prefers (plain SQL, Alembic, Flyway, sqitch, or its own ORM). Where a feature needs durable state (e.g. streaming watermarks), the storage is **caller-supplied** against a consumer-owned table. See [12 §12.9](./12-project-structure-and-packaging.md).

## 1.5 Personas & consumers

| Persona | Consumes via | Needs |
|---------|-------------|-------|
| **Python app team** | The library (`import pgfoundation`) | Simple facade, async + sync, typed results, transactions. |
| **Polyglot / non-Python team** | The service shell (REST/gRPC) | Language-neutral endpoints, auth, predictable contracts. |
| **Platform / SRE team** | Config + observability | Metrics, health checks, tunable pools, no code changes to reconfigure. |
| **Security team** | Config + audit | Secrets never in code, least-privilege, audit logging. |

## 1.6 Quality attributes (prioritized)

1. **Performance & efficiency** (G4) — the reason it exists at the infra layer.
2. **Reliability / resilience** — pool safety, retries, circuit breaking.
3. **Decoupling / maintainability** (G5, G7 requirements) — ports & adapters.
4. **Security** — secret hygiene, least privilege.
5. **Observability** — you cannot operate what you cannot see.
6. **Extensibility** — future capabilities (semantic layer, time-series) build on the foundation via seams.

## 1.7 Constraints & assumptions

- **Language/runtime:** Python 3.12+ (the scaffold uses 3.14; we target 3.12+).
- **Driver:** `psycopg` 3.x (async + sync). See [ADR-001](./adr/ADR-001-driver-psycopg3.md).
- **Service framework:** **plain Django** (ASGI, async views) + `apispec`/`openapi-core` for OpenAPI — chosen for team fluency. See [ADR-012](./adr/ADR-012-service-shell-plain-django.md) (supersedes [ADR-002](./adr/ADR-002-service-framework.md)).
- **The existing Django scaffold** in `postgresqlmodule/code` is **repurposed as the service shell** (not retired) — see [ADR-012](./adr/ADR-012-service-shell-plain-django.md). The core library stays framework-free and uses no ORM.
- Deployment targets containerized environments (Docker/K8s) but must also run as a plain library with no server.

## 1.8 Glossary

| Term | Meaning |
|------|---------|
| **Data source** | A named, independently-configured PostgreSQL database target (DSN + pool + policies). |
| **Port** | An interface (abstract contract) defined by the core. |
| **Adapter** | A concrete implementation of a port (e.g. the psycopg adapter). |
| **Registry** | The component holding all named data sources. |
| **Facade** | The single, small public entry point exposed to consumers. |
| **Unit of Work (UoW)** | An object that tracks a transactional boundary and commits/rolls back atomically. |
| **Service shell** | The optional REST/gRPC process wrapping the core library. |
