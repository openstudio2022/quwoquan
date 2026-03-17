# Assistant Mainline Milestone Board

## Purpose

This document is the single status board for the current assistant mainline
refactor. It answers three questions consistently:

- Which tasks are `completed`, `in_progress`, `pending`, or `blocker`
- What evidence is required before a task can move state
- Which milestones are already closed versus still open

It is intentionally status-oriented and should be updated as the code and test
evidence change.

## Status Rules

- `completed`: code path is landed, guarded by stable tests, and no remaining
  blocker is required for the core milestone to hold
- `in_progress`: core implementation is partially landed, but at least one
  owner path, validation layer, or exit criterion is still open
- `pending`: the implementation path or validation path exists, but the task
  has not been closed with code and evidence yet
- `blocker`: progress depends on an external constraint such as environment,
  credentials, simulator availability, or downstream compat cleanup

## Evidence Rules

- Code evidence must come from `quwoquan_app/lib/assistant/` or tightly-coupled
  UI and integration files
- Regression evidence must come from committed tests in
  `quwoquan_app/test/assistant/` or `quwoquan_app/integration_test/`
- Live verification evidence must come from a real provider request or live
  integration run, not from mocked tests
- A task cannot move from `in_progress` to `completed` if its last remaining
  requirement is explicitly marked as a blocker elsewhere in this board

## Task Matrix

| Task | Status | Evidence | Exit Criteria |
| --- | --- | --- | --- |
| `intent-owner-rebuild` | `completed` | `AssistantAgentLoop` is the orchestrated entry; `agent_loop.dart` live path first resolves typed owner state before execution; `orchestration_phase_owner_test.dart`, `full_phase_pipeline_test.dart`, `assistant_agent_loop_parity_guard_test.dart` are green | Keep legacy loop as compat bridge only; do not re-introduce owner logic outside phases |
| `followup-continuity` | `in_progress` | continuity inputs, previous intent carryover, and follow-up answer repair are guarded by `orchestration_phase_owner_test.dart` | Re-run `integration_test/assistant_manual_replay_test.dart` after owner refactors and confirm no replay regression |
| `multi-dimensional-retrieval` | `in_progress` | typed `queryTasks`, continuity-aware retrieval, and runtime consumption of phase-provided tasks are covered by `orchestration_phase_owner_test.dart`, `full_phase_pipeline_test.dart`, and `react_runtime_tool_observation_contract_test.dart` | Remove remaining execution-time fallback logic outside phase/retrieval owner paths |
| `one-pass-answer-optimization` | `completed` | phase-one direct answer shortcut, repair, gap-fill retry, and bounded-answer readiness are covered by owner and full-pipeline tests | Maintain direct-answer path as default convergence path |
| `replay-regression-upgrade` | `in_progress` | replay-related cleanup is covered by full-pipeline regression tests and the manual replay test file exists | Re-run manual replay integration on iOS after the current refactor set |
| `live-weather-e2e-milestone` | `pending` | live test entry exists in `test/assistant/minimax_live_weather_fortune_test.dart` | Produce one successful live weather run with non-degraded answer evidence |
| `fallback-dependency-burn-down-milestone` | `in_progress` | active owner path no longer depends on legacy `_resolveIntentGraph()` or ad hoc `problemClass` fallback; analyzer still shows dead helper warnings | Remove dead helpers and duplicate owner-era resolvers from `agent_loop.dart` |
| `live-provider-request-success` | `pending` | provider compat code and tests exist | Produce one confirmed real provider success trace |
| `live-provider-credential-unblock` | `blocker` | live provider tests depend on valid credentials and a non-blocked remote account | Supply valid credentials and complete a real request successfully |

## Milestones

### M1 Baseline Freeze

Definition:

- one board
- one status vocabulary
- one evidence rule set

Status: `completed`

Evidence:

- this document exists and is intended to be updated as the canonical board

### M2 Legacy Owner Burn-Down

Definition:

- `agent_loop.dart` stops carrying dead or duplicated owner/routing helpers
- execution preparation and subagent preparation stop drifting across two
  implementations

Status: `in_progress`

Required exit:

- analyzer dead-helper warnings removed from `agent_loop.dart`
- execution-preparation logic points to one resolver path

### M3 Phase Execution Owner

Definition:

- `ExecutionPhase`, `SynthesisPhase`, and `FinalizePhase` stop being thin shells
  over a large legacy monolith

Status: `in_progress`

Required exit:

- typed phase-owned services exist for execution, synthesis, and finalize
- phase files become thin coordinators

### M4 Replay Closure

Definition:

- replay survives current owner refactors end-to-end

Status: `in_progress`

Required exit:

- `assistant_manual_replay_test.dart` passes after the latest refactor set

### M5 Live Provider Closure

Definition:

- live provider request works
- live weather e2e succeeds

Status: `blocker`

Current blocker:

- credentials and/or provider account state are not yet proven usable

## Stable Guardrails

- `test/assistant/orchestration_phase_owner_test.dart`
- `test/assistant/full_phase_pipeline_test.dart`
- `test/assistant/react_runtime_tool_observation_contract_test.dart`
- `test/assistant/assistant_agent_loop_parity_guard_test.dart`

## Current Blocking Notes

- compat response keys such as `uiProcessTimelineV2` and `uiUsageStatsV1` are
  still consumed downstream, so response-shape cleanup must be coordinated
- live provider closure is not a pure code task; it depends on credentials,
  remote availability, and non-blacklisted access

## Execution Order

1. Finish legacy owner burn-down inside `agent_loop.dart`
2. Unify execution-preparation semantics on the shared resolver
3. Extract execution/synthesis/finalize owner services
4. Re-run manual replay integration
5. Close live provider verification
