# ADR-003 — Delivery model: core library + thin service shell

**Status:** Accepted
**Date:** 2026-07-22

## Context

External projects must consume the foundation. Consumers are both Python
(who benefit from in-process, low-latency access) and potentially polyglot
(who need a network API). We must expose *only a reusable API* and keep layers
decoupled.

## Decision

Ship **two distributions from one codebase**:

1. `pgfoundation` — a pure-Python **core library** (the Facade + engine).
2. `pgfoundation-service` — a **thin service shell** (plain Django ASGI / gRPC — [ADR-012](./ADR-012-service-shell-plain-django.md)) that wraps the library.

The shell is *just another consumer* of the library's public Facade; it holds no
data-access logic.

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Library core + thin service shell** | Serves Python (fast, in-proc) and polyglot (network); guaranteed parity; shell can act as a connection concentrator | Two artifacts to release | **Chosen** |
| Library only | Simplest, lowest latency | Excludes non-Python consumers | Rejected |
| Service only | Language-neutral | Forces network hop on Python callers; wastes in-proc opportunity | Rejected |

## Consequences

- **Positive:** one engine, two skins → no behavioral drift; contract tests enforce parity ([13](../13-testing-strategy.md)).
- **Positive:** in **service mode**, pooled connections are shared across a fleet — a connection concentrator that reduces total PostgreSQL backends ([09 §9.3](../09-performance.md)).
- **Positive:** library consumers avoid Django/grpc weight (separate distribution, [12](../12-project-structure-and-packaging.md)).
- **Negative / mitigation:** dual release cadence — handled with independent SemVer streams and a shared CI pipeline.
