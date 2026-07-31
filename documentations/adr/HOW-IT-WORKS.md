# How `pgfoundation` Works — Implementation Walkthrough

> This is a **walkthrough of the built code**, not a decision record. For *why*
> each choice was made, see the numbered [ADRs](./README.md) and the design docs
> in [`documentations/`](../README.md). File paths below are relative to
> `postgresqlmodule/code/`.

---

## 1. The big picture

`pgfoundation` is a low-level, reusable data-access layer over PostgreSQL,
delivered as **two packages from one codebase**:

| Package | What it is | Depends on |
|---------|-----------|------------|
| `pgfoundation/` | The **core library** — async connection management, execution, transactions, governed object invocation, streaming. Framework-free, no ORM, no Django. | psycopg 3, pydantic |
| `pgfoundation_service/` | The **service shell** — plain Django (ASGI) exposing the core over REST + OpenAPI. | `pgfoundation`, Django, apispec |

The guiding rule is **Ports & Adapters (hexagonal) + a layered stack**:
dependencies point **inward only**. The center (`core/`) is pure Python; psycopg,
Django, config sources, metrics, and auth are all *adapters at the edges*. This is
mechanically enforced by import-linter contracts ([`.importlinter`](../../postgresqlmodule/code/.importlinter)).

```mermaid
graph TB
    subgraph shell[pgfoundation_service · plain Django ASGI]
      HTTP[async views] --> DTO[Pydantic DTOs] --> AUTH[AuthGate seam]
    end
    subgraph lib[pgfoundation · core library]
      FAC[DataFoundation Facade] --> HND[DataSourceHandle]
      HND --> ACC[Access: invocation / UoW / interval / watermark]
      ACC --> REG[ConnectionRegistry]
      REG --> DEC[MeteredPool → ResilientPool]
      DEC --> DRV[psycopg driver adapter]
    end
    AUTH --> FAC
    DRV --> PG[(PostgreSQL)]
    style lib fill:#0d3,opacity:0.1
```

---

## 2. The layers, inside-out

### 2.1 Core — ports, models, errors (`pgfoundation/core/`)

The center. **Stdlib only** (zero third-party imports).

- **`models.py`** — the value objects that cross the public boundary: `QuerySpec`
  / `Query` / `Command` (SQL + bound params), `ResultSet`, `PoolPolicy`,
  `RetryPolicy`, `IsolationLevel`, `HealthStatus`; the governed-invocation types
  `ViewQuery` / `FunctionQuery` / `ProcedureCall` / `Filter` / `FilterOp` /
  `OrderBy`; and the streaming types `IntervalQuery` / `Agg` / `WatermarkCursor` /
  `Page` / `NotifyEvent`.
- **`errors.py`** — the driver-agnostic hierarchy consumers catch: `PgFoundationError`
  → `ConfigError`, `ConnectionError`, `PoolTimeoutError`, `QueryError`,
  `IntegrityError`, `TransactionError`, `TransientError`, `PermanentError`.
- **`ports.py`** — the interfaces (`typing.Protocol`) every outer piece implements:
  `ConnectionPort`, `PoolPort`, `DriverPort`, and the observability/clock seams
  `LoggerPort` / `MetricsPort` / `TracerPort` / `ClockPort`.

Because the core owns these interfaces, **everything else is swappable** — the
psycopg driver and the in-memory test `FakeDriver` both satisfy `DriverPort`
structurally.

### 2.2 Configuration — L0 (`pgfoundation/_internal/config/`)

- **`settings.py`** — typed, validated **Pydantic** models: `AppSettings` holds a
  list of `DataSourceSettings` (each with a `SecretStr` `dsn`, `PoolSettings`,
  role, `read_only`, `statement_timeout_ms`), plus `ResilienceSettings`,
  `AuthSettings`, `ObservabilitySettings`. Validators reject duplicate/empty
  data-source names and bad pool sizes **at boot** (fail-fast).
- **`loader.py`** — `load_settings(source)` accepts a **dict, YAML, or JSON** and
  resolves `${env:VAR}` / `${secret:...}` references before validation. The DSN is
  held as a `SecretStr` so it is never printed in logs or reprs.

### 2.3 Connection management — L1 (`pgfoundation/_internal/connection/registry.py`)

- **`PoolFactory`** — Abstract Factory. For each data source it builds a raw pool
  from the `DriverPort`, then **wraps it with decorators**:
  `MeteredPool(ResilientPool(raw_pool, breaker), metrics)`. Each data source gets
  its **own** circuit breaker → *bulkhead* isolation.
- **`ConnectionRegistry`** — the Registry pattern: `DataSourceName → PoolPort`.
  Built once at startup; the request path only does O(1) name lookups. `start()`
  opens all pools; `aclose()` drains them; `health()` probes each.

This is what makes "**multiple PostgreSQL connections**" real — N named data
sources, each independently pooled and tuned.

### 2.4 The driver adapter (`pgfoundation/_internal/drivers/`)

- **`psycopg_driver.py`** — the **only** place psycopg is imported (enforced).
  - `PsycopgPool` wraps `psycopg_pool.AsyncConnectionPool`. Connections are set to
    **autocommit** (via `await conn.set_autocommit(True)`), so single statements
    commit immediately and explicit transactions are managed by the Unit of Work.
    Connects are bounded by a `connect_timeout` so an unreachable DB fails fast
    instead of hanging.
  - `PsycopgConnection` implements `ConnectionPort`: `execute`, `execute_many`,
    `stream` (server-side cursor inside a short transaction), `copy_stream` (COPY),
    `listen` (LISTEN/NOTIFY), and `begin` (returns `_PsycopgTransaction`, which
    sets isolation on the connection then opens `conn.transaction()`; nested calls
    become SAVEPOINTs).
  - `errors_map.py` translates psycopg `SQLSTATE` codes into the Core error
    hierarchy (`40001`/`40P01` → `TransientError`, `23xxx` → `IntegrityError`,
    `08xxx` → `ConnectionError`, `42xxx`/`22xxx` → `QueryError`).
- **`fake.py`** — `FakeDriver`/`FakePool`/`FakeConnection`: an in-memory
  implementation so the whole stack is unit-tested with **no database**.

### 2.5 Resilience & observability (decorators)

- **`resilience/circuit_breaker.py`** — `CircuitBreaker` state machine
  (CLOSED → OPEN → HALF_OPEN). **`resilience/pool.py`** — `ResilientPool` opens the
  breaker after repeated connection failures and fast-fails `acquire` until a reset
  window elapses.
- **`observability/metered.py`** — `MeteredPool`/`MeteredConnection` time queries
  and count errors through the `MetricsPort` (the *signal vocabulary*:
  `pgf_query_duration_seconds`, `pgf_query_errors_total`, …). Defaults to
  **`observability/noop.py`** (`NoopMetrics`) so it is **zero-cost** until an
  external log project binds a real adapter (ADR-014).

Both are pure decorators around `PoolPort`/`ConnectionPort` — no business logic is
touched, and they compose transparently.

### 2.6 Data access — L2 (`pgfoundation/_internal/access/`)

- **`uow.py`** — `UnitOfWork`: pins one connection, `begin`s a transaction, and
  commits on clean exit / rolls back on exception; `savepoint()` nests.
- **`transactions.py`** — `run_transaction(pool, fn, retry)`: the **retryable
  transaction runner** that re-executes the whole body on `TransientError`
  (`40001`/`40P01`) with backoff + jitter, using an injectable `ClockPort`.
- **`invocation.py`** — the **governed object-invocation** compilers (Strategy +
  Builder): `compile_view` / `compile_function` / `compile_procedure` turn a
  *named* object call into **safe, parameterized** SQL. Identifiers are validated
  (`sql.py::safe_identifier`), values are bound, operators come from the
  `FilterOp` whitelist. **This is why clients never send raw SQL.**
- **`interval.py`** — `compile_interval` builds a `date_bin` time-bucketed query.
- **`watermark.py`** — `fetch_since` does **keyset** pagination (never `OFFSET`)
  and returns a `Page` + the next `WatermarkCursor` for resumable incremental pulls.
- **`repository.py`** — a thin optional `Repository[T]` base (no ORM identity map).

### 2.7 The public API — L3 (`pgfoundation/_internal/api/`)

- **`handle.py`** — `DataSourceHandle`: the ergonomic per-data-source surface —
  `query`/`one`/`scalar`, `execute`/`execute_many`, `transaction`/`run_transaction`,
  `stream`, `interval`, `fetch_since`, `copy_stream`, `listen`, and the **name-based**
  `view`/`function`/`procedure`, plus `view_stream`/`function_stream` for large reads.
- **`facade.py`** — `DataFoundation`: the composition entry point. `from_config` /
  `from_settings` wire the object graph (config → driver → registry → decorators →
  facade), warm the pools, and return a ready object. It exposes name-addressed
  passthroughs (`db.view("main", ...)`) and lifecycle (`start`/`aclose`, async
  context manager).

The package `__init__.py` re-exports exactly this public surface; everything under
`_internal` is private.

### 2.8 The service shell (`pgfoundation_service/`)

Plain Django on ASGI — a *thin* transport skin over the same Facade.

- **`settings.py`** — Django settings for the **web layer only** (no ORM, no
  `DATABASES`; the foundation manages its own connections).
- **`bootstrap.py`** — holds the process-wide `DataFoundation` + `AuthGate`.
- **`schemas.py`** — Pydantic **DTOs** (`ViewIn`, `FunctionIn`, `ProcedureIn`,
  `QueryIn`, `QueryOut`, …) — the source of truth for both request validation and
  the OpenAPI spec.
- **`views.py`** — **async** Django views. The recommended ones are name-based:
  `view_query_view` / `function_view` / `procedure_view`. `query_view`/`execute_view`
  (raw SQL) remain for advanced/trusted use.
- **`auth.py`** — the **AuthGate seam**: `AuthenticatorPort`/`AuthorizerPort` with
  `AllowAll` no-op defaults; **disabled by default**, fails closed if enabled
  without a provider (ADR-013).
- **`http_errors.py`** — the `@api` decorator: assigns a request-id, runs the view,
  and translates Core/auth errors into HTTP status codes (`QueryError`→400,
  `IntegrityError`→409, `PoolTimeoutError`/`ConnectionError`→503, `ConfigError`→404,
  auth→401/403). Bodies never leak SQL/credentials/stack traces.
- **`openapi.py`** — `apispec` builds the OpenAPI 3 spec **code-first from the
  Pydantic DTOs**; served at `/openapi.json`.
- **`asgi.py`** — wraps Django with an **ASGI lifespan** handler that builds the
  foundation from `PGF_CONFIG` on the serving loop at startup and drains it at
  shutdown. Also sets the Windows `SelectorEventLoop` policy (async psycopg needs it).
- **`run_local.py`** — the dev launcher: builds a uvicorn `Server` and runs
  `serve()` inside a `SelectorEventLoop` we create (bypassing uvicorn's default
  Windows loop, which async psycopg cannot use).

---

## 3. End-to-end: a request through every layer

A client calls **`POST /v1/datasources/main/view`** with a body that names a view
and passes structured filters — *no SQL*:

```json
{ "name": "v_paid_orders", "columns": ["id","amount"],
  "filters": [{"column":"customer","op":"eq","value":"bob"}], "limit": 100 }
```

```mermaid
sequenceDiagram
    participant C as Client
    participant V as view_query_view (Django async view)
    participant G as AuthGate
    participant F as DataFoundation / Handle
    participant I as compile_view (invocation)
    participant P as MeteredPool→ResilientPool→PsycopgPool
    participant DB as PostgreSQL
    C->>V: POST /view {name, filters, ...}
    V->>V: ViewIn.model_validate_json(body)   (400 on bad input)
    V->>G: check(request, "read", "main")     (no-op when auth disabled)
    V->>F: db.datasource("main").view(ViewQuery(...))
    F->>I: compile_view(spec)
    I-->>F: Query("SELECT id, amount FROM v_paid_orders WHERE customer = %(f0)s LIMIT 100", {f0:"bob"})
    F->>P: acquire()  (breaker allows? metrics timer starts)
    P->>DB: execute(parameterized SQL)
    DB-->>P: rows
    P-->>F: ResultSet(rows, rowcount, elapsed_ms)  (metrics.observe duration)
    F-->>V: ResultSet
    V-->>C: 200 {rows, row_count, elapsed_ms}  (X-Request-Id header)
```

Step by step:

1. **Transport & validation** — Django routes to `view_query_view`; the body is
   validated into a `ViewIn` DTO (a bad body → `ValidationError` → **HTTP 400** via
   the `@api` decorator).
2. **Auth** — `AuthGate.check(...)`; a pass-through while disabled, or 401/403 when
   an external auth provider is wired.
3. **Facade** — the view builds a core `ViewQuery` and calls
   `foundation.datasource("main").view(spec)`.
4. **Compile (governed)** — `compile_view` validates the object name + column
   identifiers, maps the `eq` operator, and emits a **parameterized** `Query`
   (`customer = %(f0)s`, value bound in `params`). An injection attempt in `name`
   is rejected as `QueryError` → **HTTP 400**.
5. **Pool + decorators** — the handle acquires a connection through
   `MeteredPool → ResilientPool → PsycopgPool`. The breaker gates acquisition; the
   metering decorator times the call.
6. **Execute** — `PsycopgConnection.execute` runs the SQL with bound params via a
   `dict_row` cursor and returns a `ResultSet` (with `elapsed_ms`). psycopg reuses
   a **prepared statement** because the compiled SQL is deterministic for this call
   shape.
7. **Response** — the view serializes `QueryOut{rows, row_count, elapsed_ms}`;
   Django's encoder renders `numeric` as a JSON string to preserve precision; an
   `X-Request-Id` header ties the response to logs.

The **library** path is identical minus steps 1–2: `await db.datasource("main").view(spec)`.

---

## 4. Key mechanisms, summarized

| Concern | How it works |
|---------|--------------|
| **Concurrency** | Async end-to-end (psycopg async pools + ASGI). One event loop holds many in-flight requests; concurrent DB work is bounded by pool `max_size` with fail-fast `acquire_timeout` (backpressure). Per-DS pools are bulkheads. |
| **No raw SQL from clients** | Name-based `view`/`function`/`procedure` compile to safe parameterized SQL; identifiers validated, values bound, operators whitelisted. |
| **Transactions** | `UnitOfWork` (commit/rollback + savepoints); `run_transaction` re-runs the whole body on serialization failure/deadlock with backoff. |
| **Streaming / interval / incremental** | server-side cursor `stream`; `date_bin` `interval`; keyset `fetch_since` (no `OFFSET`); `copy_stream`; `LISTEN/NOTIFY`. |
| **Resilience** | per-DS circuit breaker (fast-fail on outage); retry classification via SQLSTATE mapping; bounded connect/acquire timeouts. |
| **Observability** | emitted through `MetricsPort`/`LoggerPort`/`TracerPort`; **no-op by default**, an external log project binds the pipeline (ADR-014). |
| **Auth** | pluggable `AuthGate` seam; **disabled by default**, fails closed when enabled without a provider (ADR-013). |
| **Config** | typed Pydantic settings; dict/YAML/JSON + `${env:}`/`${secret:}`; secrets as `SecretStr`; fail-fast at boot. |
| **Schema ownership** | **none** — the foundation creates no tables and runs no migrations; consumers own all schema. |
| **Errors** | psycopg `SQLSTATE` → Core error hierarchy → HTTP status; consumers never see psycopg types. |

---

## 5. Running it (quick reference)

Nothing is pip-installed from this repo — `postgresqlmodule/code` is the import
root, and the entry points put it on `sys.path` themselves. Run everything from
there:

```bash
cd postgresqlmodule/code
PY=../venv314/Scripts/python.exe

# one-time: dependencies only
$PY -m pip install -r requirements.txt

# run the service (reads PGF_CONFIG; default port 8600)
export PGF_CONFIG="$PWD/config/pgfoundation.yaml"
$PY -m pgfoundation_service.run_local          # or F5 in VS Code

# tests
$PY -m pytest -q                               # unit + service (no DB needed)
PGF_TEST_DSN=postgresql://user:pass@host:5432/db $PY -m pytest -q   # + live PostgreSQL
../venv314/Scripts/lint-imports.exe            # architecture contracts
```

Latest verified state: **69 tests pass** with `PGF_TEST_DSN` set (65 pass and the
4 live-PostgreSQL tests skip without it) and **4/4 import-linter contracts kept**.

---

## 6. Where to read more

- **Full design** — [`documentations/`](../README.md) (or the rendered
  `documentations/pgfoundation-design.html`). Layered design: doc 03; data access &
  concurrency: doc 07; streaming & interval: doc 16; service shell: doc 08.
- **Decisions** — [ADRs](./README.md): psycopg driver (001), library+service (003),
  plain-Django shell (012), auth seam (013), observability integration (014), etc.
- **Top-level usage** — [`README.md`](../../README.md) and the code notes in
  [`postgresqlmodule/code/README.md`](../../postgresqlmodule/code/README.md).
