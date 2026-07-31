# pgfoundation — implementation

Reference implementation of the design in [`documentations/`](../../documentations).
**Not an installable package** — the service is consumed over its HTTP API. This
directory *is* the import root; the entry points add it to `sys.path` themselves.

| Directory | What it is |
|-----------|-----------|
| [`pgfoundation/`](./pgfoundation) | The **core engine** — framework-free, no ORM, no Django. Internal. |
| [`pgfoundation_service/`](./pgfoundation_service) | The **service shell** — plain Django (ASGI) + apispec OpenAPI + auth seam. The consumer-facing surface. |
| [`tests/`](./tests) | `unit/` (in-memory FakeDriver, no DB) · `integration/` (live PostgreSQL) · `service/` (HTTP shell) |
| [`config/`](./config) | `pgfoundation.yaml` — data sources, pools, resilience |

## What's implemented (by roadmap phase, doc 14)

| Phase | Delivered | Where |
|-------|-----------|-------|
| **0 Foundations** | Core ports/models/errors, L0 config (+`${env:}`/`${secret:}`), psycopg driver, connection registry, `DataFoundation` facade | `pgfoundation/core/`, `pgfoundation/_internal/{config,drivers,connection,api}` |
| **1 Core access** | Multi-DB, Unit of Work, **retryable `run_transaction`** (40001/40P01), savepoints, `execute_many`, Repository | `pgfoundation/_internal/access` |
| **1.5 Streaming/interval** | Server-side `stream`, `IntervalQuery` bucketing (`date_bin`), keyset **`fetch_since`** watermark, `copy_stream`, `listen` | `pgfoundation/_internal/access/{interval,watermark}`, driver |
| **2 Resilience/obs** | Per-DS **circuit breaker** + resilient pool, **metering** via `MetricsPort` (no-op default, ADR-014) | `pgfoundation/_internal/{resilience,observability}` |
| **3 Service shell** | Async Django views, Pydantic DTOs, **code-first OpenAPI** (apispec), **auth seam disabled by default** (ADR-013), HTTP error translation | `pgfoundation_service/` |

## Run the tests

Uses the repo's `venv314`. From **this** directory:

```bash
PY=../venv314/Scripts/python.exe

$PY -m pytest -q                         # all suites → 65 passed, 4 skipped
PGF_TEST_DSN=postgresql://user:pass@host:5432/db $PY -m pytest -q   # + live PostgreSQL
../venv314/Scripts/lint-imports.exe      # architecture contracts → 4 kept, 0 broken
```

## Run the service

```bash
PGF_CONFIG="$PWD/config/pgfoundation.yaml" ../venv314/Scripts/python.exe \
    -m pgfoundation_service.run_local
# OpenAPI at /openapi.json, docs at /docs/, health at /v1/health
```

`DJANGO_SETTINGS_MODULE` defaults to `pgfoundation_service.settings`.

## Notes / platform

- **No package installation.** `asgi.py` and `run_local.py` each put this
  directory on `sys.path`, so the service starts from a checkout regardless of
  cwd or ASGI server. `pyproject.toml` does the same for pytest; it carries
  tooling config only and has no `[build-system]`/`[project]` table.
- **Async psycopg on Windows** needs a `SelectorEventLoop` (the default
  `ProactorEventLoop` is unsupported). uvicorn selects a compatible loop; tests
  set the policy in `tests/conftest.py`.
- **Auth** is a disabled-by-default seam — the open service must run on a trusted
  network until an external auth project is integrated (ADR-013).
- **Observability** is emitted through ports with no-op defaults; bind an
  external log project's adapter to collect it (ADR-014).
- **Schema**: the foundation owns no tables and does no schema init — consumers
  own all schema (doc 12 §12.9).
