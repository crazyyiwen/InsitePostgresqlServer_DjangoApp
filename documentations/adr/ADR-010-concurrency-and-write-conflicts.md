# ADR-010 — Concurrency & write-conflict handling policy

**Status:** Accepted
**Date:** 2026-07-24

## Context

PostgreSQL uses **MVCC**: readers and writers never block each other, so pure
reads (batch extracts, streaming, interval queries, dashboards) never see write
conflicts. The only conflict class is **write–write on the same row/key**. The
foundation already maps `40001` (serialization failure) and `40P01` (deadlock) to
retry-eligible `TransientError`, and `23505` (unique violation) to a
non-retryable `IntegrityError` ([07 §7.9](../07-data-access-and-transactions.md)).

Two things were **not** yet explicit and are easy to get wrong:

1. A serialization failure invalidates the **whole transaction**, not one
   statement — so statement-level retry is insufficient; you must re-run the
   entire transaction body.
2. **Lost updates** from application-side read-modify-write, and **overlapping
   scheduled writers** (e.g. the 15-min/1-h aggregation refresh), need a stated
   policy.

## Decision

1. **Default isolation = READ COMMITTED**, config-overridable per transaction;
   REPEATABLE READ / SERIALIZABLE chosen deliberately where cross-row invariants
   require it.
2. Provide a **retryable transaction runner** `run_transaction(fn, isolation,
   retry)` that re-executes the whole transaction body on `40001`/`40P01` with
   backoff + jitter. The context-manager `transaction()` form remains for
   transactions that don't need auto-retry. Statement-level retry stays
   **disabled inside an open transaction**.
3. The transaction body passed to `run_transaction` must be **idempotent / free of
   non-DB side effects** (it may run more than once); side effects happen after
   commit.
4. **Lost-update prevention is chosen per write pattern**, all supported by the
   basic write APIs:
   - atomic `UPDATE … SET x = x + n` for counters/totals;
   - `INSERT … ON CONFLICT DO UPDATE` upserts for aggregation tables & ingest;
   - `SELECT … FOR UPDATE [SKIP LOCKED]` for claim/queue patterns;
   - **optimistic concurrency** via a `version`/`updated_at` column + affected-rows
     check (documented convention, raising a retryable conflict).
5. **Scheduled/exclusive jobs use `pg_advisory_lock`** (or `SELECT … FOR UPDATE
   SKIP LOCKED`) so overlapping runs cannot double-write.
6. Defaults (isolation, a 3-attempt transaction retry) are **config-driven, never
   hard-coded**.

Full design: [07 §7.10 Concurrency & Write-Conflict Handling](../07-data-access-and-transactions.md).

## Options considered

| Topic | Chosen | Rejected | Why |
|-------|--------|----------|-----|
| Retry granularity | **Transaction-level runner** for `40001`/`40P01` | Statement-level retry only | A serialization failure aborts the whole transaction; a statement retry can't fix it |
| Default isolation | **READ COMMITTED** | SERIALIZABLE everywhere | Fewer serialization retries; escalate only where invariants need it |
| Lost updates | **Per-pattern (atomic/upsert/optimistic/pessimistic)** | One global locking scheme | Different write shapes have different cheapest-correct answers |
| Exclusive jobs | **Advisory lock / `SKIP LOCKED`** | Rely on scheduler never overlapping | Schedulers *do* overlap (retries, clock skew, manual runs) |

## Consequences

- **Positive:** correct-by-construction handling of the realistic conflict cases; reads stay conflict-free by MVCC; the aggregation-refresh and ingest paths are safe under overlap.
- **Positive:** the runner + optimistic-version convention close the one real gap (transaction-level retry) without an ORM or heavy locking framework.
- **Negative / mitigation:** `run_transaction` bodies must be side-effect-free — documented explicitly, and enforced in review/tests ([13](../13-testing-strategy.md)) with a concurrent-writer integration test that asserts retry convergence.
- **Scope:** the foundation supplies mechanisms + defaults; each consumer selects the per-write-pattern policy. Application-level distributed transactions across multiple databases remain out of scope (use sagas/outbox in the consumer).
