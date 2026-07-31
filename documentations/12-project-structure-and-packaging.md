# 12 — Project Structure & Packaging

How the design maps onto files, packages, and releases. This governs the *future*
implementation; **no code is written yet.**

## 12.1 Monorepo, two distributable packages

One repository, two Python distributions that release independently:

- `pgfoundation` — the core library (no web framework deps).
- `pgfoundation-service` — the service shell (depends on `pgfoundation` + **Django** + apispec/openapi-core + optional grpc).

This keeps library consumers free of Django/grpc weight while sharing one codebase.

## 12.2 Proposed directory layout

```
insitepostgresqldbserver_djangoapp/
├─ documentations/                     # ← this design (already here)
├─ postgresqlmodule/
│  └─ code/
│     ├─ pyproject.toml                 # workspace / build config
│     ├─ requirements.txt               # (dev convenience; deps declared in pyproject)
│     ├─ packages/
│     │  ├─ pgfoundation/               # === CORE LIBRARY (distribution 1) ===
│     │  │  ├─ pyproject.toml
│     │  │  └─ src/pgfoundation/
│     │  │     ├─ __init__.py           # PUBLIC surface re-exports (see doc 11)
│     │  │     ├─ py.typed
│     │  │     ├─ core/                 # ports, value objects, errors (zero 3rd-party deps)
│     │  │     │  ├─ ports.py
│     │  │     │  ├─ models.py
│     │  │     │  └─ errors.py
│     │  │     └─ _internal/            # PRIVATE — no stability promise
│     │  │        ├─ config/            # L0: providers, settings, composition root
│     │  │        ├─ connection/        # L1: registry, pool factory, health, routing
│     │  │        ├─ access/            # L2: pipeline, uow, repository, mapper
│     │  │        ├─ drivers/           # adapters: psycopg3 (DriverPort impl)
│     │  │        ├─ resilience/        # retry, circuit breaker, timeouts (decorators)
│     │  │        └─ observability/     # logging, metrics, tracing adapters
│     │  └─ pgfoundation_service/       # === SERVICE SHELL (distribution 2) · plain Django ===
│     │     ├─ pyproject.toml
│     │     ├─ manage.py                 # (repurposed from the existing scaffold)
│     │     └─ src/pgfoundation_service/
│     │        ├─ asgi.py                # ASGI entrypoint (async)
│     │        ├─ settings.py            # Django settings (web layer only; no ORM for the foundation)
│     │        ├─ urls.py                # routes → async views; /openapi.json; /docs
│     │        ├─ views/                 # async Django views calling the Facade
│     │        ├─ schemas.py             # Pydantic DTOs (source of truth for OpenAPI)
│     │        ├─ openapi.py             # apispec spec builder + openapi-core validation
│     │        ├─ grpc/                  # grpcio servicers (optional)
│     │        ├─ middleware/            # auth, rate-limit, correlation, tracing
│     │        └─ cli.py                 # `pgfoundation` ops CLI
│     ├─ proto/                         # protobuf definitions for gRPC
│     ├─ config/
│     │  ├─ pgfoundation.example.yaml   # sample config (NO secrets)
│     │  └─ profiles/                   # dev / staging / prod overlays
│     └─ tests/
│        ├─ unit/                       # ports mocked; no DB
│        ├─ integration/                # real PG via testcontainers
│        ├─ contract/                   # REST/gRPC contract tests
│        └─ load/                       # perf/soak scripts
└─ ...
```

> The existing Django scaffold (`core/`, `manage.py`) is superseded by this
> layout; see [ADR-002](./adr/ADR-002-service-framework.md) for the migration note.

## 12.3 Dependency boundaries (enforced)

`import-linter` contracts fail CI if violated:

1. **Layered contract:** `core` ⇐ `config` ⇐ `connection` ⇐ `access` ⇐ facade; no upward imports.
2. **Core purity:** `pgfoundation.core.*` (ports) may import stdlib only — not psycopg, and no web framework (**Django** stays out of the whole `pgfoundation` library).
3. **Driver isolation:** psycopg may be imported *only* under `_internal/drivers/`.
4. **Public-API contract:** nothing outside `pgfoundation` imports `pgfoundation._internal`.
5. **Shell contract:** `pgfoundation_service` imports only the public `pgfoundation` surface (plus Django/apispec/openapi-core); **Django is confined to the shell** and never appears in `pgfoundation`.

## 12.4 `pyproject.toml` highlights (core)

```toml
[project]
name = "pgfoundation"
requires-python = ">=3.12"
dependencies = [
  "psycopg[binary,pool]>=3.2",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
]
[project.optional-dependencies]
otel = ["opentelemetry-sdk", "opentelemetry-instrumentation"]  # THIN adapter to the external log project (ADR-014); pipeline lives there
vault = ["hvac"]
aws  = ["boto3"]

[tool.hatch.build.targets.wheel]
packages = ["src/pgfoundation"]
```

Core stays lean; secret-manager and observability integrations are **optional
extras** so consumers pull only what they use (performance & footprint). The
`otel` extra is only a **thin adapter** binding the foundation's observability
ports to the external log/observability project — the foundation does not ship a
telemetry pipeline ([ADR-014](./adr/ADR-014-observability-external-integration.md)).

## 12.5 `pyproject.toml` highlights (service)

```toml
[project]
name = "pgfoundation-service"
dependencies = [
  "pgfoundation",
  "django>=5.0",              # web layer only (ASGI, async views); no ORM for the foundation
  "apispec>=6.6",            # code-first OpenAPI 3 from Pydantic schemas
  "openapi-core>=0.19",      # request/response validation vs the spec (contract tests)
  "uvicorn[standard]>=0.30", # or daphne/gunicorn+uvicorn worker — an ASGI server
]
[project.optional-dependencies]
grpc = ["grpcio>=1.64"]      # optional gRPC surface
[project.scripts]
pgfoundation = "pgfoundation_service.cli:main"
```

## 12.6 Versioning & release

- **SemVer** for `pgfoundation`; the public surface ([11](./11-public-api-reference.md)) defines "breaking."
- Independent version streams for library vs service.
- Changelog per package; deprecation policy = one minor cycle of warnings.
- Build with Hatch; publish to the internal package index; wheels are pure-Python (psycopg binary wheel carries the native bits).

## 12.7 Runtime distribution

- **Library mode:** `pip install pgfoundation`; import and go.
- **Service mode:** container image built from `pgfoundation-service`; entrypoint is an **ASGI server** (`uvicorn`/`daphne`/`gunicorn`-with-uvicorn-worker) running the Django app, plus an optional `grpcio` server; config mounted or env-injected; secrets from the platform secret manager.

## 12.8 Tooling baseline

| Concern | Tool |
|---------|------|
| Build/packaging | Hatch |
| Lint/format | Ruff |
| Types | mypy / pyright (strict on public surface) |
| Arch rules | import-linter |
| Tests | pytest, pytest-asyncio, testcontainers, pytest-benchmark |
| Security | pip-audit, bandit, secret-scanning in CI |

## 12.9 No schema ownership — consumers own all tables

The foundation owns **no database tables** and performs **no schema initialization**.
It is a connection / query / transaction layer only; every table is defined and created
by the **consuming project**, with whatever tool it prefers (plain SQL, Flyway, sqitch,
or its own ORM/migrations — the foundation imposes none and ships none).

- No `schema/` directory, no `.sql` DDL files, and no schema/migration runner are shipped.
- Where a feature needs durable state — e.g. streaming **watermarks**
  ([16 §16.5](./16-streaming-and-interval-fetching.md)) — the storage location is
  **caller-supplied / configured**, against a table the consumer owns.
- The foundation still uses **no ORM** for its own data access
  ([ADR-012](./adr/ADR-012-service-shell-plain-django.md)): it speaks plain,
  parameterized SQL through its query/transaction API
  ([07](./07-data-access-and-transactions.md)).
