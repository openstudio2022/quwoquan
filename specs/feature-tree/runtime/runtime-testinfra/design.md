# Design: runtime-testinfra

> Status: implementation in progress.

## Approach

The `runtime/testinfra` package provides test database helpers (testcontainers MongoDB, embedded Postgres, miniredis)
for L2 Cloud Contract Tests. The `Suite` type aggregates all test database instances under a single lifecycle.

## Key Decisions

- `NewSuite(t, opts...)` attaches cleanup via `t.Cleanup` automatically
- MongoDB uses testcontainers `mongo:7-jammy` for real driver behavior; falls back to `TEST_MONGO_URI` env var
- Redis uses `miniredis` for speed (no container spin-up for unit tests)
- Embedded Postgres for SQL schemas when needed

## Constraints

- Follows `specs/00_MASTER_DEVELOPMENT_FLOW.md`
- No production code imports allowed in testinfra package
