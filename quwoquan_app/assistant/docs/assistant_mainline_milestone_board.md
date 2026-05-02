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
  `quwoquan_app/test/assistant/` or `quwoquan_app/test/common|alpha|beta|gamma`
- Live verification evidence must come from a real provider request or live
  integration run, not from mocked tests
- A task cannot move from `in_progress` to `completed` if its last remaining
  requirement is explicitly marked as a blocker elsewhere in this board

## Task Matrix

| Task | Status | Evidence | Exit Criteria |
| --- | --- | --- | --- |
| `intent-owner-rebuild` | `completed` | `AssistantAgentLoop` is the orchestrated entry; owner state is resolved before phase execution; `orchestration_phase_owner_test.dart`, `full_phase_pipeline_test.dart`, `assistant_agent_loop_parity_guard_test.dart` are green | Do not re-introduce owner logic outside phases and phase owner services |
| `followup-continuity` | `in_progress` | continuity inputs, previous intent carryover, and follow-up answer repair are guarded by `orchestration_phase_owner_test.dart` | Re-run `test/common/assistant/assistant_environment_smoke_test.dart` after owner refactors and confirm no environment regression |
| `multi-dimensional-retrieval` | `completed` | typed `TaskGraph`, projection-only `searchPlans`, centralized retrieval tool selection, and runtime consumption of phase-provided tasks are covered by `retrieval_tool_selection_policy_test.dart`, `app_search_tool_runtime_test.dart`, `orchestration_phase_owner_test.dart`, `full_phase_pipeline_test.dart`, and `react_runtime_tool_observation_contract_test.dart` | Keep `TaskGraph` as the execution truth source and keep `searchPlans` projection-only |
| `one-pass-answer-optimization` | `completed` | phase-one direct answer shortcut, repair, gap-fill retry, and bounded-answer readiness are covered by owner and full-pipeline tests | Maintain direct-answer path as default convergence path |
| `m0-replay-baseline` | `in_progress` | retired in favor of `assistant_scenarios.json` plus `test/common/assistant/assistant_environment_smoke_test.dart`; `test/assistant/replay_record_factory_test.dart` still guards shared replay payload extraction | Close after scenario fixture coverage fully replaces current replay artifacts |
| `replay-regression-upgrade` | `in_progress` | replay-related cleanup is covered by full-pipeline regression tests and environment smoke tests | Re-run assistant environment smoke on iOS after the current refactor set |
| `typed-mainline-persistence-closure` | `in_progress` | `FinalizeRunner`, `persisted_assistant_turn.dart`, and `AssistantConversationController` now carry typed mainline fields; regression is tracked in `finalize_runner_test.dart` | Close only after typed contracts are persisted, reloadable, and visible to UI/transcript consumers without relying on current-only fields |
| `live-weather-e2e-milestone` | `completed` | `flutter test test/assistant/minimax_live_weather_fortune_test.dart --dart-define=LIVE_TEST=true` passed in this verification pass | Keep live weather proof separate from local-only closure and reclassify as blocker only when credentials/provider/network fail |
| `fallback-dependency-burn-down-milestone` | `in_progress` | active owner path no longer depends on current `_resolveIntentGraph()` or ad hoc `problemClass` fallback; remaining work is dead-code and current-marker cleanup around phase owner/runtime edges | Remove dead helpers and duplicate owner-era resolvers from the remaining phase owner/runtime files |
| `live-provider-request-success` | `completed` | live weather provider test completed with a non-degraded response in this verification pass | Re-run before release or when provider credentials change |
| `live-provider-credential-unblock` | `completed` | current credentials/account/network were usable for the live weather verification pass | Keep future credential or account failures classified as external blockers |

## Milestones

### M1 Baseline Freeze

Definition:

- one board
- one status vocabulary
- one evidence rule set

Status: `completed`

Evidence:

- this document exists and is intended to be updated as the canonical board

### M2 Current Owner Burn-Down

Definition:

- phase owner/runtime files stop carrying dead or duplicated owner/routing helpers
- execution preparation and subagent preparation stop drifting across two
  implementations

Status: `in_progress`

Latest evidence:

- `assistant/docs/m6_centralized_verification_report.md`
- local contract/UI matrix passed
- simulator weather and stock replay now pass under typed gates
- M6 is not fully accepted because current mainline regression tests still fail
  on removed `searchPlans`, `problemClass`, and compatibility expectations

Required exit:

- analyzer dead-helper warnings removed from phase owner/runtime files
- execution-preparation logic points to one resolver path

### M3 Phase Execution Owner

Definition:

- `ExecutionPhase`, `SynthesisPhase`, and `FinalizePhase` stop being thin shells
  over a large current monolith

Status: `in_progress`

Required exit:

- typed phase-owned services exist for execution, synthesis, and finalize
- phase files become thin coordinators

### M4 Replay Closure

Definition:

- replay survives current owner refactors end-to-end

Status: `in_progress`

Latest evidence:

- weather and stock M0 replay selected cases pass with
  `ASSISTANT_REPLAY_REPEAT_COUNT=1`
- weather/stock replay gates now read structured `understandingResult`,
  `taskGraph`, and entity refs instead of answer-text regexes or deleted
  `resolvedGeoScope`

Required exit:

- `assistant_manual_replay_test.dart` passes after the latest refactor set
- M0 replay corpus produces repeat-stable baseline packs and all selected cases are M1-eligible

### M5 Live Provider Closure

Definition:

- live provider request works
- live weather e2e succeeds
- note: this is only the live-verification slice of milestone 5, not the full local code closure

Status: `completed`

Current evidence:

- `flutter test test/assistant/minimax_live_weather_fortune_test.dart --dart-define=LIVE_TEST=true`
- final `structuredResponse.understandingSnapshot` stayed populated in the live weather path
- answer was non-degraded in this verification pass

### M5 Local Closure

Definition:

- typed mainline state is persisted and reloadable
- UI/transcript consumers can observe typed mainline fields
- remaining current residues are honestly tracked instead of being claimed deleted

Status: `completed`

Required exit:

- `finalize_runner_test.dart` proves typed mainline persistence
- local validation covers contract, finalize, and UI/provider regression paths
- typed residue list is kept current for `AssistantPlanView/searchPlans/local_context`

### M6 Centralized Verification

Definition:

- verify M5 local closure status before claiming final completion
- run local T1/T2/T4 validation matrix
- separate live-provider closure from local verification
- produce a final pass/fail/blocker/not-covered report

Status: `in_progress`

Required exit:

- M5 local closure status is explicitly marked `completed`, `in_progress`, or `blocker`
- `assistant_contracts_roundtrip_test.dart`, `finalize_runner_test.dart`, and UI/provider regression paths are run or assigned explicit blockers
- typed mainline fields are proven persisted and visible to UI/transcript consumers
- live provider weather status is proven with one non-degraded run; future credential/provider/network failures remain separate external blockers

## Stable Guardrails

- `test/assistant/orchestration_phase_owner_test.dart`
- `test/assistant/full_phase_pipeline_test.dart`
- `test/assistant/react_runtime_tool_observation_contract_test.dart`
- `test/assistant/assistant_agent_loop_parity_guard_test.dart`

## Current Blocking Notes

- current response keys have been removed from the active path; keep regression
  gates enabled so downstream consumers do not re-introduce them
- live provider closure can regress for external reasons; keep credential,
  remote availability, and account access failures classified separately from
  code regressions

## Execution Order

1. Finish current owner burn-down inside phase owner/runtime files
2. Unify execution-preparation semantics on the shared resolver
3. Extract execution/synthesis/finalize owner services
4. Re-run manual replay integration
5. Close live provider verification
