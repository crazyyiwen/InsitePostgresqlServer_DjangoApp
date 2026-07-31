# PostgreSQL Database Foundation Server — Design Documentation

> **Codename:** `pgfoundation`
> **Status:** Design (no implementation yet)
> **Last updated:** 2026-07-22

This directory contains the complete architecture and design plan for the
**PostgreSQL Database Foundation Server** — a low-level infrastructure component
that provides a unified, high-performance, reusable data-access foundation over
**multiple PostgreSQL databases**.

It is delivered in **two consumable forms**:

1. **A pure-Python core library** (`pgfoundation`) — installable via `pip`, imported directly by other Python projects.
2. **A thin network service shell** (`pgfoundation-service`) — a REST/gRPC server that wraps the core so non-Python projects can consume it.

---

## Design principles (the north star)

These are the seven requirements that drive every decision in this design:

| # | Requirement | Where it is addressed |
|---|-------------|-----------------------|
| 1 | Support **multiple** PostgreSQL database connections | [06 — Connection Management](./06-connection-management.md) |
| 2 | Work as **infrastructure / lower-level code** | [02 — Architecture](./02-architecture-overview.md), [03 — Layered Design](./03-layered-design.md) |
| 3 | **No hard-coded** values anywhere | [05 — Configuration](./05-configuration.md) |
| 4 | **Efficient** with best-in-class performance | [09 — Performance](./09-performance.md) |
| 5 | Proper **design patterns** | [04 — Design Patterns](./04-design-patterns.md) |
| 6 | Expose a **set of reusable, useful basic APIs** for external projects (not one call) | [11 — Public API Reference](./11-public-api-reference.md) |
| 7 | Built on **clearly decoupled layers** | [03 — Layered Design](./03-layered-design.md) |
| N1 | Support a **dynamic semantic layer** (reduce coding, dynamic search) | *deferred — to be designed later* |
| N2 | DB server **supports the semantic case** via generic seams — no hard-coding, patterns, clean code | [01 §1.3.1](./01-vision-scope-requirements.md), [03 §3.4.5](./03-layered-design.md) |
| N3 | **Flexible development** as new requirements arrive | *deferred — to be designed later* |
| N4 | Support **streaming** & **interval data fetching** | [16 — Streaming & Interval Fetching](./16-streaming-and-interval-fetching.md) |
| N5 | **API AuthN/AuthZ seam** — disabled by default, real impl from a separate project | [08 §8.5.1](./08-service-shell.md), [ADR-013](./adr/ADR-013-auth-pluggable-seam.md) |
| N6 | **Observability integrated from a separate log project** — instrument via ports, don't build the pipeline | [10 §10.1](./10-observability-security-resilience.md), [ADR-014](./adr/ADR-014-observability-external-integration.md) |

> **N1–N3** were added following the Insite API design update, which places a
> *Dynamic Data Product, Semantic & Serving Layer* between the database and UI.
> That layer is **deferred — to be designed later**; the foundation only exposes
> the generic **seams** it will need (N2). Governing principle:
> **consumers query governed data products, not raw tables; new requirements change
> metadata/semantic models, not the stable DB contract.**

---

## Reading order

| Doc | Title | What you'll learn |
|-----|-------|-------------------|
| [01](./01-vision-scope-requirements.md) | Vision, Scope & Requirements | The problem, goals, non-goals, personas, glossary |
| [02](./02-architecture-overview.md) | Architecture Overview | The big picture — hexagonal + layered, C4 context/container |
| [03](./03-layered-design.md) | Layered Design | Each layer, its contracts, and dependency rules |
| [04](./04-design-patterns.md) | Design Patterns Catalog | Every pattern used and *why* |
| [05](./05-configuration.md) | Configuration Management | The "no hard-coding" strategy |
| [06](./06-connection-management.md) | Connection Management | Multi-DB registry, pooling, health, routing |
| [07](./07-data-access-and-transactions.md) | Data Access & Transactions | Execution pipeline, Unit of Work, repositories, **concurrency & write-conflict handling** |
| [08](./08-service-shell.md) | Service Shell | REST/gRPC/SSE/Arrow delivery + **protocol choice per use case** (batch / aggregation / real-time) |
| [09](./09-performance.md) | Performance Engineering | Pooling, prepared statements, COPY, pipelining |
| [10](./10-observability-security-resilience.md) | Observability, Security & Resilience | Logging, metrics, tracing, secrets, retries, circuit breaking |
| [11](./11-public-api-reference.md) | Public API Reference | The **catalog of reusable basic APIs** external code depends on |
| [12](./12-project-structure-and-packaging.md) | Project Structure & Packaging | Repo layout, packaging, versioning |
| [13](./13-testing-strategy.md) | Testing Strategy | Unit, integration, contract, load, chaos |
| [14](./14-roadmap-and-extensibility.md) | Roadmap & Extensibility | Phased delivery + extensibility seams |
| [16](./16-streaming-and-interval-fetching.md) | **Streaming & Interval Data Fetching** | Cursor streaming, interval/windowed queries, watermark fetch, streaming ingest (N4) |
| [ADRs](./adr/) | Architecture Decision Records | The consequential choices, recorded |

> **Deferred — to be designed later** (design files intentionally removed from
> this plan; they would build on the foundation's generic seams):
> - **Semantic & Serving Layer** — metric registry, semantic compiler, policy, aggregate planner, serving.
> - **Time-Series capability** — TimescaleDB hypertables, continuous aggregates, retention.
>
> *(Doc 15 is intentionally absent — the semantic-layer design was removed pending
> a later redesign; the streaming/interval doc keeps its number 16.)*

---

## One-paragraph summary

`pgfoundation` is a **hexagonal (ports-and-adapters), layered** data-access
platform. A driver-agnostic **core** defines ports (interfaces) for connections,
execution, transactions, and configuration; a **psycopg 3** adapter implements
them. A **Connection Registry** manages any number of named PostgreSQL data
sources, each with its own tuned async pool. Every configuration value flows
through a layered **configuration provider chain** (env → file → secret manager)
so *nothing* is hard-coded. The public surface is a **curated set of reusable
basic APIs** (read, write, transaction, streaming, interval, bulk/batch, admin) —
one import, many composable building blocks — while everything behind it is
private and replaceable. A separate **service shell** (plain Django on ASGI)
exposes that same core over REST/gRPC without leaking internals. It also supports
**streaming and interval data fetching** — server-side cursor streams,
time-bucketed/windowed queries, and resumable watermark-based incremental pulls —
sized for interval meter data and real-time feeds. Higher-level concerns — a
**Semantic & Serving Layer** and a **Time-Series** capability — are **deferred, to
be designed later** on top of the foundation. The foundation stays generic and
exposes clean **seams** (composable `QuerySpec`, materialized-view lifecycle,
access-filter hook, `DriverPort`, pluggable interval bucketing) so that future
work plugs in with no core change.
