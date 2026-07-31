# PostgreSQL Database Foundation Server (`pgfoundation`)

A hardened, reusable **infrastructure layer** for talking to PostgreSQL — so every
downstream project shares one correct, fast, observable data-access foundation
instead of re-implementing connection handling, pooling, retries, transactions,
and configuration.

It is consumed **over its HTTP API** — there is no installable package. One
codebase, two internal layers:

- **`pgfoundation`** — the framework-free core (engine): pooling, transactions,
  streaming, resilience. Internal; not published or pip-installable.
- **`pgfoundation_service`** — a thin **plain-Django (ASGI) shell** that exposes
  the core over REST + OpenAPI. **This is the consumer-facing surface.**

> **Status:** working reference implementation — **69 tests passing** with
> `PGF_TEST_DSN` set (65 pass and the 4 live-PostgreSQL tests skip without it) and
> **4/4 architecture contracts** enforced. See
> [`postgresqlmodule/code/README.md`](postgresqlmodule/code/README.md).

---

## Repository layout

```
InsitePostgresqlServer_DjangoApp/
├─ documentations/                  # Full design plan (16 docs + ADRs) + rendered HTML
│  └─ pgfoundation-design.html       #   open this in a browser for the whole design
└─ postgresqlmodule/
   ├─ venv314/                       # Python 3.14 virtualenv (deps installed here)
   └─ code/                          # ← the import root (put on sys.path by the entry points)
      ├─ config/                     # pgfoundation.yaml — data sources, pools, resilience
      ├─ pgfoundation/               # === CORE ENGINE (internal) ===
      │  ├─ core/                    #   ports, models, error hierarchy
      │  └─ _internal/               #   private layers: access, config, drivers, resilience
      ├─ pgfoundation_service/       # === SERVICE SHELL (plain Django, ASGI) ===
      ├─ tests/                      # unit (no DB) · integration (live PG) · service
      ├─ .importlinter               # architecture contracts
      ├─ pyproject.toml              # tooling config only — NOT an installable package
      └─ requirements.txt
```

Design rationale for every choice lives in [`documentations/`](documentations/)
(start with [`README.md`](documentations/README.md), or open the combined
`documentations/pgfoundation-design.html`).

---

## 1. Prerequisites

- **Python 3.12+** (this repo uses 3.14 via `postgresqlmodule/venv314`).
- **A reachable PostgreSQL** (the foundation manages its own connections; it does
  **not** create tables or run migrations — your project owns all schema).

Dependencies are already installed in `postgresqlmodule/venv314`. In shell
examples below, `PY` is that interpreter:

```bash
# from the repo root
PY=postgresqlmodule/venv314/Scripts/python.exe        # Windows
# PY=postgresqlmodule/venv314/bin/python              # POSIX
```

If you need to (re)install into a fresh venv:

```bash
$PY -m pip install -r postgresqlmodule/code/requirements.txt
```

**There is nothing to install from this repo itself.** `pgfoundation` and
`pgfoundation_service` are not packages you `pip install` — they are imported
from `postgresqlmodule/code`, which the entry points (`asgi.py`, `run_local.py`)
add to `sys.path` themselves. Run commands from that directory and everything
resolves.

---

## 2. Quick start — the core API (in-repo scripts only)

> External projects consume this service over **HTTP** ([§5](#5-run-the-service-django-asgi)).
> The Python API below is not installable; it is available to scripts and workers
> that live in — or are run from — `postgresqlmodule/code`.

```python
import asyncio
from pgfoundation import DataFoundation, Query, Command

async def main():
    # Config can be a dict, a YAML/JSON path, or use ${env:...} / ${secret:...}
    config = {
        "datasources": [
            {"name": "main", "dsn": "postgresql://user:pass@localhost:5432/mydb",
             "pool": {"min_size": 1, "max_size": 10}},
        ]
    }

    async with await DataFoundation.from_config(config) as db:
        # read
        n = await db.datasource("main").scalar(Query("SELECT count(*) FROM orders"))
        print("orders:", n)

        # write inside an atomic transaction (commits on clean exit)
        async with db.transaction("main") as uow:
            await uow.execute(Command(
                "INSERT INTO orders(customer_id, total) VALUES (%(c)s, %(t)s)",
                {"c": 42, "t": "19.90"},
            ))

asyncio.run(main())
```

Run it from the code root, which is the import root:

```bash
cd postgresqlmodule/code && ../venv314/Scripts/python.exe your_script.py
```

> **Windows note:** async psycopg requires a `SelectorEventLoop`. Wrap `main()`
> with one (uvicorn does this for you in service mode):
> ```python
> import asyncio, selectors
> with asyncio.Runner(loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())) as r:
>     r.run(main())
> ```

---

## 3. The reusable API

You import **one package**; everything under `pgfoundation._internal` is private.
The building blocks (all on `db.datasource(name)` or via `db.<op>(name, ...)`):

| Category | API | Purpose |
|----------|-----|---------|
| **Read** | `query` · `one` · `scalar` | Run a parameterized read |
| **Write** | `execute` · `execute_many` | Write / batched writes |
| **Transaction** | `transaction(...)` (Unit of Work) | Atomic block + savepoints |
| | `run_transaction(fn, retry=...)` | Retries the whole body on serialization failure/deadlock |
| **Streaming** | `stream(spec)` | Constant-memory server-side cursor |
| | `listen(channel)` | `LISTEN/NOTIFY` change stream |
| **Interval** | `interval(IntervalQuery(...))` | Time-bucketed fetch (15-min/hourly…) |
| | `fetch_since(spec, cursor)` | Resumable keyset/watermark fetch |
| **Bulk** | `copy_stream(table, rows)` | Streaming `COPY` ingest |
| **Admin** | `datasource` · `names` · `health` | Resolve / list / health |

Values are **always** bound parameters (`%(name)s` / `%s`) — never string-formatted.
Errors are driver-agnostic: catch `QueryError`, `IntegrityError`, `PoolTimeoutError`,
`TransientError`, etc. — never psycopg types.

Examples:

```python
from pgfoundation import Agg, IntervalQuery, WatermarkCursor, Query, RetryPolicy

h = db.datasource("main")

# stream a large result at flat memory
async for row in h.stream(Query("SELECT * FROM big_table WHERE day=%(d)s", {"d": day})):
    handle(row)

# 15-minute interval buckets
async for bucket in h.interval(IntervalQuery(
        source="readings", time_column="ts", start=t0, end=t1,
        every="15 minutes", metrics=[Agg("kwh", "sum")], group_by=["meter_id"])):
    publish(bucket)

# resumable incremental "what's new since last time"
page = await h.fetch_since(Query("SELECT ts, id, kwh FROM readings", {}),
                           WatermarkCursor(order_by=("ts", "id")), limit=1000)
save(page.next_watermark)   # durable checkpoint

# auto-retry a transaction on 40001/40P01 (keep the body side-effect free)
async def move(uow):
    await uow.execute(Command("UPDATE acct SET bal = bal - %(a)s WHERE id=%(s)s", {...}))
await h.run_transaction(move, retry=RetryPolicy(max_attempts=3))
```

---

## 4. Configuration

Config is externalized (nothing hard-coded). A YAML example:

```yaml
# pgfoundation.yaml
datasources:
  - name: orders-primary
    dsn: ${secret:orders/primary/dsn}     # resolved from a secret manager / env
    role: primary
    pool: { min_size: 2, max_size: 20, acquire_timeout_seconds: 3 }
  - name: orders-replica
    dsn: ${env:ORDERS_REPLICA_DSN}        # or straight from an env var
    role: replica
    read_only: true

resilience:
  retry: { max_attempts: 3, base_backoff_ms: 20, jitter: true }
  circuit_breaker: { enabled: true, failure_threshold: 5, reset_timeout_seconds: 30 }

auth:            # service shell only — pluggable seam, disabled by default
  enabled: false
observability:   # integrate an external log project; default no-op
  provider: none
```

Load it: `await DataFoundation.from_config("pgfoundation.yaml")`.
Multiple named data sources → multiple independent pools (bulkheads).

---

## 5. Run the service (Django, ASGI)

**Easiest — VS Code:** open *Run and Debug* and launch **"pgfoundation-service
(localhost:8600)"** (see [`.vscode/launch.json`](.vscode/launch.json)).

**From a terminal** — the local runner sets the correct event loop on Windows and
builds the pools on the serving loop via an ASGI lifespan:

```bash
cd postgresqlmodule/code
export PGF_CONFIG="$PWD/config/pgfoundation.yaml"   # your connection config
export PGF_PORT=8600
../venv314/Scripts/python.exe -m pgfoundation_service.run_local
```

`DJANGO_SETTINGS_MODULE` defaults to `pgfoundation_service.settings`, and the
runner puts `postgresqlmodule/code` on `sys.path` itself — so any ASGI server
works too:

```bash
cd postgresqlmodule/code && ../venv314/Scripts/python.exe -m uvicorn \
    pgfoundation_service.asgi:application --port 8600
```

The service starts even if the database is momentarily down — `GET /v1/health`
then reports `degraded`/`down` until it's reachable.

Endpoints — the **recommended** interface is name-based invocation (clients name
a DB object + pass parameters; **no SQL crosses the wire**):

| Method & path | Purpose |
|---------------|---------|
| `POST /v1/datasources/{name}/view` | **Query a view/table by name** + structured filters |
| `POST /v1/datasources/{name}/function` | **Call a function by name** + args |
| `POST /v1/datasources/{name}/procedure` | **Call a stored procedure by name** + args |
| `GET  /v1/datasources` | List configured data sources |
| `GET  /v1/health` | Health / readiness |
| `GET  /openapi.json` · `GET /docs/` | OpenAPI 3 spec / docs |
| `POST /v1/datasources/{name}/query` · `/execute` | *Advanced/trusted only* — raw parameterized SQL |

### 5.1 Examples — call views, functions & stored procedures by name

The caller sends the **object name + parameters**; the server compiles safe,
parameterized SQL internally (identifiers validated, values bound). Every response
below is **real output** from the running service.

> **Set-up SQL** used by these examples (run once against your database):
> ```sql
> CREATE TABLE demo_orders (id int primary key, customer text, amount numeric, status text);
> INSERT INTO demo_orders VALUES
>   (1,'alice',19.90,'paid'),(3,'bob',42.00,'paid'),(4,'bob',7.50,'paid');
> CREATE VIEW v_paid_orders AS
>   SELECT id, customer, amount FROM demo_orders WHERE status='paid';
> CREATE FUNCTION fn_orders_by_customer(cust text)
>   RETURNS TABLE(id int, amount numeric) LANGUAGE sql AS $$
>     SELECT id, amount FROM demo_orders WHERE customer = cust ORDER BY id; $$;
> CREATE PROCEDURE sp_customer_stats(
>     IN cust text, INOUT order_count int DEFAULT NULL, INOUT total numeric DEFAULT NULL)
>   LANGUAGE plpgsql AS $$ BEGIN
>     SELECT count(*), COALESCE(sum(amount),0) INTO order_count, total
>     FROM demo_orders WHERE customer = cust; END; $$;
> ```

**1) Query a VIEW by name** — pass `columns`, `filters`, `order_by`, `limit`
(never SQL). `op` is one of `eq ne lt le gt ge in not_in like ilike between is_null is_not_null`:

```bash
curl -X POST localhost:8600/v1/datasources/main/view \
  -H 'content-type: application/json' \
  -d '{"name":"v_paid_orders","columns":["id","customer","amount"],
       "filters":[{"column":"customer","op":"eq","value":"bob"}],
       "order_by":[{"column":"id"}]}'
```
```json
{"rows": [{"id": 3, "customer": "bob", "amount": "42.00"},
          {"id": 4, "customer": "bob", "amount": "7.50"}],
 "row_count": 2, "elapsed_ms": 11.4}
```
*(A **materialized view** is called the same way — just its name.)*

**2) Call a FUNCTION by name** — `args` may be a named map or a positional list.
Add `"scalar": true` for a scalar function:

```bash
curl -X POST localhost:8600/v1/datasources/main/function \
  -H 'content-type: application/json' \
  -d '{"name":"fn_orders_by_customer","args":{"cust":"bob"}}'
```
```json
{"rows": [{"id": 3, "amount": "42.00"}, {"id": 4, "amount": "7.50"}],
 "row_count": 2, "elapsed_ms": 1.2}
```

**3) Call a stored PROCEDURE by name** — positional `args` (pass `null` for
`OUT`/`INOUT` params; their values come back as a row):

```bash
curl -X POST localhost:8600/v1/datasources/main/procedure \
  -H 'content-type: application/json' \
  -d '{"name":"sp_customer_stats","args":["bob",null,null]}'
```
```json
{"rows": [{"order_count": 2, "total": "49.50"}], "row_count": 1, "elapsed_ms": 2.1}
```

**Optional fields:** all three accept `"schema": "public"` to qualify the object.

**Why name-based (not raw SQL):**

- **No injection surface** — object names are validated identifiers; an attempt
  like `{"name":"v_paid_orders; DROP TABLE demo_orders"}` returns **HTTP 400**.
- **No schema leakage / no arbitrary-table access** — callers can only reach the
  objects you expose, the way a database *infrastructure* server should behave.
- **High throughput** — the generated SQL is deterministic per call shape, so
  psycopg reuses **prepared statements**; large view/function reads can stream.
- **Functions vs. procedures** — a `CREATE FUNCTION` returns rows (via `/function`);
  a true `CREATE PROCEDURE` uses `/procedure` (`CALL`) and returns data only via
  `INOUT`/`OUT` params (as above) or a refcursor (wrap those in a `RETURNS TABLE`
  function). Procedures that `COMMIT` internally work because statements run in
  autocommit.
- **`numeric`/`decimal`** serialize as JSON **strings** (`"42.00"`) to keep exact precision.

> **Advanced/trusted only:** `POST .../query` and `.../execute` still accept raw
> parameterized SQL (`{"sql":"…","params":{…}}`) for internal tooling/migrations.
> Keep them off the public surface (auth/policy); prefer the name-based calls for
> application traffic.

**Auth** is a pluggable seam **disabled by default** — until a separate auth
project is integrated, run the service only on a trusted network / behind a
gateway. Set `auth.enabled: true` in production (it fails closed if no provider is
registered). **Observability** is emitted through ports with no-op defaults; bind
an external log project's adapter to collect it.

---

## 6. Run the tests

All tests run in one command from the code root — no installation needed
(`pyproject.toml` puts it on `sys.path` for pytest):

```bash
cd postgresqlmodule/code
PY=../venv314/Scripts/python.exe

# everything: core unit (in-memory FakeDriver, no DB) + service shell
$PY -m pytest -q                       # → 65 passed, 4 skipped

# add the live integration tests (skipped unless PGF_TEST_DSN is set)
PGF_TEST_DSN='postgresql://user:pass@host:5432/db' $PY -m pytest -q

# architecture contracts (import-linter): layering, core purity, driver isolation
../venv314/Scripts/lint-imports.exe    # → 4 kept, 0 broken
```

---

## 7. What's implemented vs. deferred

**Implemented & tested:** multi-DB pooling, config chain, query/execute,
transactions + savepoints + retryable transaction, streaming, interval bucketing,
watermark fetch, `COPY`, `LISTEN/NOTIFY`, circuit breaker + metering, the Django
REST shell with OpenAPI, and the disabled-by-default auth seam.

**Deferred by design** (documented, not built — see the ADRs): the semantic/serving
layer, the time-series (TimescaleDB) capability, gRPC/Arrow surfaces, vendored
Swagger UI assets, and real secret-manager / observability adapters. The
foundation **owns no tables and does no schema initialization** — your project
owns all schema.

---

## 8. Where to learn more

- **Design plan:** [`documentations/`](documentations/) — open
  `documentations/pgfoundation-design.html` for the full rendered document, or
  start at [`documentations/README.md`](documentations/README.md).
- **Implementation notes:** [`postgresqlmodule/code/README.md`](postgresqlmodule/code/README.md).
- **Decisions (ADRs):** [`documentations/adr/`](documentations/adr/).
