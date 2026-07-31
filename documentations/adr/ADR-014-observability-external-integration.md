# ADR-014 — Observability is integrated from an external log project, not built here

**Status:** Accepted
**Date:** 2026-07-24

## Context

The foundation needs logs, metrics, and traces, but the stakeholder's constraint
is explicit:

> Logs, metrics, and traces should **not be implemented from scratch**. They come
> from an **individual log/observability project**; this project just needs to
> **integrate** them.

The organization owns a separate observability/log project (collectors, exporters,
dashboards, log storage). A generic data foundation should **instrument** its code
but must not own that pipeline — the same "provide the seam, not the
implementation" stance already taken for auth ([ADR-013](./ADR-013-auth-pluggable-seam.md))
and the semantic/time-series layers.

## Decision

Split observability into **instrumentation (here)** vs **pipeline (the external
log project)**:

1. The foundation defines observability **ports** and emits telemetry through them:
   - `LoggerPort` — structured log events,
   - `MetricsPort` — counters/gauges/histograms,
   - `TracerPort` — spans + context propagation.
2. It ships **no-op defaults** (`NoopLogger`/`NoopMetrics`/`NoopTracer`, Null
   Object) so the foundation runs standalone at **zero overhead** when nothing is
   wired.
3. It **integrates** the organization's **external log/observability project** by
   binding those ports to **thin adapters** at the composition root (e.g. an
   OpenTelemetry adapter, or an adapter the log project ships). The choice is
   config-driven.
4. The foundation **does not implement** the telemetry backend/pipeline —
   exporters, OTLP/collector config, dashboards, log aggregation/storage,
   alerting. That is owned by the external project.
5. What the foundation *does* own is **what to emit**: the instrumentation points
   and the metric/span/log-event vocabulary (names, labels, correlation IDs) so
   the external project has a stable, well-defined signal to collect.

Design: [10 §10.1](../10-observability-security-resilience.md).

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Instrument via ports, integrate external project (chosen)** | No reinvented telemetry stack; org's observability project owns the pipeline; foundation stays generic; zero-cost when off | Must agree a stable signal vocabulary across the boundary | **Chosen** |
| Implement logging/metrics/tracing stack here | Turnkey | Reinvents the log project; couples the foundation to specific backends; contradicts the constraint | Rejected |
| No observability hooks | Simplest | Nothing to integrate later without invasive changes; blind in production | Rejected |

## Consequences

- **Positive:** the external log project owns exporters/collectors/dashboards; the foundation just emits through ports — swap the backend with **no foundation change**.
- **Positive:** default no-op keeps library-mode and tests at zero telemetry overhead (Null Object; no `if enabled` branches).
- **Positive:** a documented, stable **signal vocabulary** (metric names, span names, log fields, correlation IDs — [10 §10.1](../10-observability-security-resilience.md)) gives the log project a firm contract to consume.
- **Negative / mitigation:** the instrumentation-vocabulary is a cross-project contract — mitigated by versioning it alongside the public API and documenting it in one place.
- **Boundary:** optional adapter dependencies (e.g. OpenTelemetry SDK) stay **optional extras** in packaging ([12 §12.4](../12-project-structure-and-packaging.md)); the core has none.
