# ADR-006 — Streaming & interval data fetching: cursors, keyset watermarks, and a bucketing seam

**Status:** Accepted
**Date:** 2026-07-23

## Context

The Insite domain is interval- and stream-heavy: 15-minute meter readings,
streaming sources (Kafka/Redpanda), streaming aggregation, real-time dashboards,
and very large time-range scans. A new requirement (**N4**) states the database
server must support **streaming** and **interval data fetching**. We must decide
the mechanisms without pulling in TimescaleDB (deferred to a future time-series capability).

## Decision

1. **Streaming reads** use **server-side named cursors** exposed as async
   generators with a **pinned connection** and **bounded-queue backpressure**;
   `itersize` is config-tunable.
2. **Interval/windowed fetching** is a declarative `IntervalQuery` compiled by a
   **pluggable Bucketing Strategy**: the foundation ships generic PostgreSQL
   (`date_bin`/`date_trunc` + `generate_series`); a TimescaleDB
   `time_bucket`/continuous-aggregate Strategy could be supplied later by a
   **future time-series capability** (deferred, to be designed later).
3. **Incremental fetching** uses **keyset pagination + a durable watermark**,
   **never `OFFSET`** — resumable and idempotent for periodic polling.
4. **Streaming ingest** provides streaming `COPY` and `LISTEN/NOTIFY` now;
   **logical-replication/CDC** is a reserved port, not built.
5. **Long streams run on a dedicated streaming pool** (bulkhead) so they cannot
   starve OLTP latency SLOs.
6. **Streaming delivery** (chunked/SSE/gRPC-streaming/Arrow) lives only in the
   service shell; the core exposes async iterators.

Full design: [16 — Streaming & Interval Data Fetching](../16-streaming-and-interval-fetching.md).

## Options considered

| Topic | Chosen | Rejected alternative | Why |
|-------|--------|----------------------|-----|
| Deep/interval pagination | **Keyset + watermark** | `LIMIT/OFFSET` | OFFSET is O(n) on large tables; keyset is constant-time and resumable |
| Large reads | **Server-side cursors** | Materialize full result | Constant memory; supports unbounded/large sets |
| Time bucketing | **Pluggable Strategy: generic in foundation** | Hard-code `time_bucket` | Works on vanilla PG; a TimescaleDB Strategy is deferred to a future time-series capability |
| Change streams | **LISTEN/NOTIFY now, CDC seam** | Build full logical-replication CDC in v1 | CDC is heavy; defer behind a port to control scope |
| Stream isolation | **Dedicated streaming pool** | Share the OLTP pool | Bulkhead prevents long scans starving interactive queries |

## Consequences

- **Positive:** interval readings and large scans stream at flat memory; periodic ingest jobs resume exactly via watermark; OLTP latency is protected by the streaming bulkhead.
- **Positive:** works on plain PostgreSQL today; a future time-series capability's TimescaleDB acceleration could slot in later with no caller change (pluggable Strategy).
- **Positive:** a future semantic layer could expose interval fetching as a governed data product; its aggregate planner would target pre-aggregated sources when present.
- **Negative / mitigation:** streaming lifecycle (pinned connections, cursor cleanup, cancellation) is error-prone — mitigated by context-managed release, timeouts/idle caps, and chaos tests ([13](../13-testing-strategy.md)).
- **Deferred:** CDC/logical replication and Arrow Flight remain reserved ports — additive, no core change. TimescaleDB bucketing is deferred to a future time-series capability.
