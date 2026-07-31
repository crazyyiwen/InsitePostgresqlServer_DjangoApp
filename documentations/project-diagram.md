# pgfoundation — Project Diagram

Visual overview of the **PostgreSQL Database Foundation Server**: its packages,
layers, adapters, external systems, request flow, and deployment. See
[HOW-IT-WORKS](./adr/HOW-IT-WORKS.md) for the narrated walkthrough and
[the design docs](./README.md) for rationale.

---

## 1. System architecture

Two packages from one codebase; dependencies point **inward** to a pure core.
Everything at the edges (psycopg, Django, log/auth projects) is a swappable adapter.

```mermaid
graph TB
    subgraph clients[Consumers]
      PYAPP[Python app<br/>imports the library]
      REST[REST client · browser · AI agent]
      OPS[SRE / dashboards]
    end

    subgraph shell["pgfoundation_service — plain Django (ASGI) · L4 delivery"]
      VIEWS["async views<br/>/view · /function · /procedure<br/>/query · /execute · /health"]
      AUTH[AuthGate seam<br/>disabled by default]
      OAPI["OpenAPI (apispec + Pydantic DTOs)<br/>/openapi.json · /docs"]
      ERR[error translation<br/>Core error → HTTP status]
    end

    subgraph lib[pgfoundation — core library · framework-free]
      FAC["L3 · DataFoundation Facade + DataSourceHandle"]
      ACC["L2 · Access<br/>invocation compilers · Unit of Work · run_transaction<br/>interval · watermark · repository"]
      L1["L1 · ConnectionRegistry + PoolFactory"]
      DEC["decorators<br/>MeteredPool → ResilientPool (circuit breaker)"]
      DRV["driver adapter · psycopg 3"]
      CORE["Core · ports · models · errors<br/>(stdlib only, zero deps)"]
    end

    subgraph ext[External systems / seams]
      PG[("PostgreSQL<br/>N named data sources")]
      LOG["external log / observability project<br/>(MetricsPort · LoggerPort · TracerPort)"]
      AUTHP["external auth project<br/>(Authenticator/Authorizer ports)"]
    end

    subgraph deferred[Deferred — separate higher-level projects]
      SEM["Semantic & Serving Layer"]
      TS["Time-Series server (TimescaleDB)"]
    end

    PYAPP --> FAC
    REST --> VIEWS
    OPS --> OAPI
    VIEWS --> AUTH --> FAC
    OAPI -.describes/validates.-> VIEWS
    ERR -.wraps.-> VIEWS
    FAC --> ACC --> L1 --> DEC --> DRV --> PG
    ACC -. uses ports .-> CORE
    L1 -. uses ports .-> CORE
    DRV -. implements DriverPort .-> CORE
    DEC -. emits metrics .-> LOG
    AUTHP -. registers adapters .-> AUTH
    SEM -. would depend on .-> FAC
    TS -. would depend on .-> FAC

    style CORE fill:#2da44e,color:#fff
    style lib fill:#0d3,opacity:0.06
    style deferred stroke-dasharray:4 4,color:#8b949e
```

---

## 2. Layered dependency rule (inward only)

Enforced in CI by import-linter contracts: the core imports only stdlib; psycopg
lives only in the driver adapter; Django never enters the core library.

```mermaid
graph LR
    L4["L4 · Delivery<br/>(Django shell)"] --> L3
    L3["L3 · Facade / API"] --> L2
    L2["L2 · Access<br/>(execute, UoW, invocation, streaming)"] --> L1
    L1["L1 · Connection<br/>(registry, pools, decorators)"] --> L0
    L0["L0 · Config<br/>(settings, loader)"] --> CORE
    L4 -.-> CORE
    L3 -.-> CORE
    L2 -.-> CORE
    L1 -.-> CORE
    CORE["Core (ports · models · errors)"]
    XCUT["cross-cutting: resilience · observability"]
    XCUT -.decorates.-> L1
    style CORE fill:#2da44e,color:#fff
```

---

## 3. Request flow — a governed `POST /view`

A client names a view + filters (no SQL); the foundation compiles safe,
parameterized SQL and runs it through the pooled connection.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant V as Django async view
    participant G as AuthGate
    participant F as Facade / Handle
    participant I as compile_view
    participant P as Pool (metered, resilient, psycopg)
    participant DB as PostgreSQL
    C->>V: POST /view {name, filters, limit}
    V->>V: validate DTO (400 on bad body)
    V->>G: check(read, "main")   (no-op when auth off)
    V->>F: handle.view(ViewQuery(...))
    F->>I: compile_view(spec)
    I-->>F: parameterized Query (values bound)
    F->>P: acquire() (breaker gate · metrics timer)
    P->>DB: execute(SQL, params)
    DB-->>P: rows
    P-->>F: ResultSet(rows, rowcount, elapsed_ms)
    F-->>V: ResultSet
    V-->>C: 200 {rows, row_count, elapsed_ms} + X-Request-Id
```

---

## 4. Multiple data sources (bulkheads)

Each named data source has its own pool + circuit breaker, so one busy or failing
database cannot starve the others.

```mermaid
graph LR
    REG[ConnectionRegistry]
    REG -->|orders-primary| P1[Pool + breaker] --> DB1[(primary)]
    REG -->|orders-replica| P2[Pool + breaker] --> DB2[(replica)]
    REG -->|analytics| P3[Pool + breaker] --> DB3[(analytics)]
    REG -->|... N| PN[Pool + breaker] --> DBN[(...)]
```

---

## 5. Package & module structure

```mermaid
graph TB
    subgraph repo[postgresqlmodule/code]
      subgraph core[pgfoundation · core engine]
        C_CORE[core/<br/>ports · models · errors]
        C_CFG[_internal/config/<br/>settings · loader]
        C_CONN[_internal/connection/<br/>registry · PoolFactory]
        C_DRV[_internal/drivers/<br/>psycopg · fake · errors_map]
        C_RES[_internal/resilience/<br/>circuit_breaker · pool]
        C_OBS[_internal/observability/<br/>metered · noop]
        C_ACC[_internal/access/<br/>invocation · uow · transactions<br/>interval · watermark · sql · repository]
        C_API[_internal/api/<br/>facade · handle]
        C_INIT[__init__.py<br/>public surface]
      end
      subgraph svc[pgfoundation_service · Django shell]
        S_APP[asgi · settings · urls · run_local]
        S_VIEW[views · schemas · openapi]
        S_SEAM[auth · bootstrap · http_errors]
      end
    end
    svc -->|depends on public surface| C_INIT
    C_INIT --- C_API --- C_ACC --- C_CONN --- C_CFG --- C_CORE
    C_DRV -.-> C_CORE
    C_RES -.-> C_CONN
    C_OBS -.-> C_CONN
```

---

## 6. Deployment topology

```mermaid
graph LR
    subgraph libmode[Library mode]
      APP[Consumer Python app] --> LIB[pgfoundation<br/>in-process]
      LIB --> PGa[(PostgreSQL)]
    end
    subgraph svcmode[Service mode]
      CL[Any client] -->|REST + OpenAPI| SVC["pgfoundation_service<br/>(uvicorn ASGI, N workers)"]
      SVC --> LIB2[pgfoundation] --> PGb[(PostgreSQL)]
      SVC -.telemetry.-> OBS[external log project]
    end
```

*Service mode also acts as a **connection concentrator**: a fleet of stateless
service pods shares one bounded pool set, so PostgreSQL sees far fewer backends
than every app pooling independently.*
