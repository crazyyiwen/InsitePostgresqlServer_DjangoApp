# ADR-013 — API auth is a pluggable seam, disabled by default, integrated externally

**Status:** Accepted
**Date:** 2026-07-24

## Context

The service shell needs API **authentication and authorization** eventually, but
the stakeholder's constraint is explicit:

> Support API AuthN/AuthZ for **future** implementation. It can be **disabled
> now**; the real AuthN/AuthZ will be **integrated from a separate project**. Do
> **not** implement it in this (foundation) project.

Auth strategy is also organization-specific (API keys vs JWT vs mTLS; RBAC vs
ABAC; per-tenant scopes) — exactly the kind of policy a generic foundation should
*enable*, not *hard-code*. This mirrors how the semantic layer and time-series are
deferred to separate projects.

## Decision

1. The shell defines an **auth seam** — two ports:
   - `AuthenticatorPort.authenticate(request) -> Principal | None`
   - `AuthorizerPort.authorize(principal, action, resource) -> bool`
2. **Default bindings are no-ops** (`AllowAllAuthenticator` → anonymous principal;
   `AllowAllAuthorizer` → `True`). So **auth is disabled by default** and the
   service runs open out of the box.
3. A **config flag `auth.enabled`** (default `false`) controls enforcement:
   - `false` → no-ops wired; requests pass through.
   - `true` → the adapters registered by the **separate auth project** are used
     (AuthN → `401`, AuthZ → `403`).
   - `true` **with no provider registered** → the shell **fails closed** (refuses
     to start) — it never runs silently open while claiming auth is on.
4. The foundation **does not implement** any real authenticator/authorizer. The
   separate project plugs in by registering adapters for the two ports — **no
   foundation change**.
5. AuthN/AuthZ are shell-only (L4); the **core library has no auth concept**.

Design: [08 §8.5.1](../08-service-shell.md); security notes: [10 §10.2](../10-observability-security-resilience.md).

## Options considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Pluggable seam, disabled by default, external impl (chosen)** | Meets the constraint exactly; generic foundation; org picks strategy later; no core change to integrate | Ships open by default (mitigated: trusted-network + fail-closed-when-enabled) | **Chosen** |
| Implement auth now in the shell | Turnkey | Contradicts the constraint; bakes an opinion (JWT? RBAC?) into a generic foundation | Rejected |
| No auth hook at all | Simplest | Integrating auth later would require invasive shell changes | Rejected |
| Enabled-but-permissive default | "On" by default | Silent false sense of security; ambiguous | Rejected in favor of explicit `enabled` + fail-closed |

## Consequences

- **Positive:** the separate auth project owns strategy (API key/JWT/mTLS, RBAC/ABAC, per-data-source/operation policy) and plugs in via two ports with no foundation change.
- **Positive:** the core library stays auth-free; auth is confined to the L4 shell.
- **Positive:** rate limiting keys off the authenticated principal when auth is on, and per-IP when off.
- **Negative / mitigation — default-open:** until integrated, the shell enforces nothing. Mitigations: run only on a trusted network / behind a gateway or mesh mTLS; production config profiles set `auth.enabled = true`; enabling without a registered provider **fails closed**.
- **Follow-up:** when the auth project lands, add its adapters + a contract test that a request is `401`/`403` as expected with `auth.enabled = true`.
