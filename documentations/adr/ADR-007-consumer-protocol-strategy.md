# ADR-007 — Consumer-facing protocol strategy (per use case)

**Status:** Accepted
**Date:** 2026-07-24

## Context

Downstream service APIs will consume the `pgfoundation` service over the network
in several distinct workload shapes. Choosing one protocol for everything is
wrong: batch bulk transfer, scheduled incremental ETL, and live browser charts
have opposing needs (throughput vs. control vs. simplicity/reach). We keep **one
core** (the L3 Facade) and surface it through **multiple protocols**, each matched
to a workload ([08 — Service Shell](../08-service-shell.md)).

Three concrete use cases must be decided:

- **Case 1 — Batch:** fetch a large dataset from the database in one go.
- **Case 2 — Scheduled aggregation:** refresh aggregation tables every 15 min / 1 h.
- **Case 3 — Real-time charts:** stream analytics to live dashboard charts.

## Decision

| Case | Primary protocol | Data movement | Control plane | Backed by |
|------|------------------|---------------|---------------|-----------|
| **1 · Batch big-data fetch** | **Arrow Flight** (or gRPC server-streaming) | columnar/streamed bulk | **Async job API** (`POST /batch/jobs` → poll / webhook) when long-running | cursor streaming + Arrow ([16 §16.3](../16-streaming-and-interval-fetching.md)) |
| **2 · 15-min / 1-h aggregation refresh** | **No client streaming protocol** — a **scheduled internal worker** (library mode); trigger via **REST/gRPC job call** or **Kafka/Redpanda event** | internal `COPY` / `INSERT … SELECT` into aggregate tables | scheduler (cron/Airflow/Celery) or event bus | watermark/interval incremental fetch ([16 §16.4–16.5](../16-streaming-and-interval-fetching.md)); aggregate planning is a deferred higher-level concern |
| **3 · Real-time analytics charts** | **SSE** (browser) / **gRPC server-streaming** (internal service) | one-way event stream | HTTP connection lifecycle | `LISTEN/NOTIFY` + interval queries ([16 §16.6–16.7](../16-streaming-and-interval-fetching.md)) |

### Rationale per case

**Case 1 — Batch, fetch big data at once → Arrow Flight + async job.**
A large one-shot extract is throughput-bound and analytics-shaped. **Arrow Flight**
(columnar, gRPC-based, streamed) moves it far faster than text JSON and lands
directly in pandas/Spark/BI with zero re-parsing. A single synchronous REST
response that materializes the whole set is explicitly rejected (timeouts, memory,
no resumability). If the extract is long-running, the **async job pattern**
(`202 Accepted` + `job_id`, then poll or webhook) decouples the caller from the
runtime; the bytes still flow over Arrow Flight / gRPC streaming. `LIMIT/OFFSET`
paging is rejected in favor of **keyset** so a resumed/retried pull has no gaps
or dupes.

**Case 2 — Aggregation refresh every 15 min / 1 h → scheduled worker, not a wire stream.**
This is **write-side incremental ETL**, not a consumer stream, so it needs no
streaming protocol at all. Run it as a **scheduled background worker** using the
library in-process; it reads only new rows via the **watermark/keyset incremental
fetch** and bucketed **interval queries**, then writes with `COPY` / `INSERT …
SELECT` into the aggregate tables. Expose control (not data) two ways: a
lightweight **REST/gRPC "run job" endpoint** for external orchestrators, or a
**Kafka/Redpanda event** for fully decoupled triggering (the bus, DLQ, and retry
already exist in the Insite design). If a future time-series capability is added,
these refreshes could instead become **continuous aggregates** and the worker
shrinks to a policy.

**Case 3 — Real-time charts → SSE (browser) or gRPC streaming (internal).**
Live charts are one-way server→client. For **browsers**, **SSE** is the simplest
correct choice: native `EventSource`, auto-reconnect, plain HTTP, no extra
proxy — fed by `LISTEN/NOTIFY` and short interval queries. WebSocket is reserved
for the rare bidirectional/interactive case. If the consumer is an **internal
service** rather than a browser, prefer **gRPC server-streaming** for native
backpressure and typed messages. Polling REST on a timer is rejected (latency +
load). End-to-end backpressure is mandatory ([16 §16.8](../16-streaming-and-interval-fetching.md)).

## Options considered (and why not)

| Tempting choice | Rejected because |
|-----------------|------------------|
| One big **JSON REST** response for Case 1 | Full materialization, timeouts, no resumability, slow text encoding |
| **`LIMIT/OFFSET`** paging for large pulls | O(n) deep pages; gaps/dupes on retry — keyset is constant-time & resumable |
| A **streaming socket** for Case 2 | It's internal ETL; a stream adds cost and buys nothing |
| **Polling REST** for Case 3 charts | Latency and needless DB load vs. push (SSE/gRPC) |
| **gRPC to browsers** for Case 3 | Needs grpc-web proxy; SSE is simpler and browser-native |

## Consequences

- **Positive:** each workload uses the cheapest protocol that meets its needs; all three wrap the **same Facade**, so behavior is identical and adding a protocol is a new adapter, not a core change.
- **Positive:** batch and aggregation share the resumable watermark/interval primitives; charts share the `LISTEN/NOTIFY` + interval primitives — minimal new surface.
- **Negative / mitigation:** more than one protocol to secure, document, and test. Mitigation: **start with REST + SSE + the async job API**, and add **Arrow Flight** / **gRPC streaming** only when a real bulk or internal-streaming consumer needs them.
- **Follow-up:** the `POST /batch/jobs` async-job contract and the Arrow Flight endpoint are specified in [08 §8.9](../08-service-shell.md).
