# Architecture Decision Records (ADRs)

Each ADR captures one consequential decision: the context, the options weighed,
the decision, and its consequences. ADRs are immutable once accepted; a new ADR
supersedes an old one rather than editing it.

> **Companion (not an ADR):** [HOW-IT-WORKS.md](./HOW-IT-WORKS.md) — a detailed
> walkthrough of how the built code works, layer by layer, with an end-to-end
> request trace.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](./ADR-001-driver-psycopg3.md) | PostgreSQL driver: psycopg 3 | Accepted |
| [ADR-002](./ADR-002-service-framework.md) | Service-shell framework: FastAPI (retire Django scaffold) | ~~Accepted~~ **Superseded by ADR-012** |
| [ADR-003](./ADR-003-library-and-service.md) | Delivery model: core library + thin service shell | Accepted |
| [ADR-006](./ADR-006-streaming-and-interval-fetching.md) | Streaming & interval fetching: cursors, keyset watermarks, bucketing seam | Accepted |
| [ADR-007](./ADR-007-consumer-protocol-strategy.md) | Consumer-facing protocol strategy (batch / aggregation / real-time) | Accepted |
| [ADR-010](./ADR-010-concurrency-and-write-conflicts.md) | Concurrency & write-conflict handling policy | Accepted |
| [ADR-012](./ADR-012-service-shell-plain-django.md) | Service shell: **plain Django** (ASGI) + apispec + openapi-core (supersedes ADR-002) | Accepted |
| [ADR-013](./ADR-013-auth-pluggable-seam.md) | API auth is a **pluggable seam, disabled by default**, integrated externally | Accepted |
| [ADR-014](./ADR-014-observability-external-integration.md) | Observability is **integrated from an external log project**, not built here | Accepted |

> **Deferred (design files removed — to be designed later):** the *semantic &
> serving layer* and the *time-series* capability, along with their ADRs, were
> removed from the plan; they will be designed later on top of the foundation's
> generic seams.

## Template

```
# ADR-NNN — <title>
Status: Proposed | Accepted | Superseded by ADR-XXX
Date: YYYY-MM-DD
Context: <forces at play>
Decision: <what we chose>
Options considered: <alternatives + why not>
Consequences: <positive / negative / follow-ups>
```
