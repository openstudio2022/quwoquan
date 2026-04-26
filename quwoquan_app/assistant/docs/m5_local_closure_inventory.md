# M5 Local Closure Inventory

## Purpose
This document is the Milestone 5 local-closure evidence artifact for:
- honest M1-M4 status audit
- typed-mainline persistence closure
- local validation scope
- live-provider blocker separation

It does not claim live provider success. That remains a separate M5 live-closure slice.

## Current Milestone Audit
### M1
- Status: accepted at contract layer
- Evidence:
  - `lib/assistant/contracts/system_context_envelope.dart`
  - `lib/assistant/contracts/understanding_result_contract.dart`
  - `lib/assistant/contracts/task_graph_contract.dart`
  - `lib/assistant/contracts/orchestrator_state_contract.dart`
  - `lib/assistant/contracts/turn_synthesis_state_contract.dart`
  - `test/assistant/assistant_contracts_roundtrip_test.dart`
- Honest note:
  - M1 only closes typed contract shape.
  - Runtime mainline deletion is not complete in M1.

### M2
- Status: accepted
- Landed:
  - `app_search` / `app_action` contracts and routing skeleton exist
  - runtime factory registers the new tool names
  - `app_search` frozen filters / result fields / metadata schema are aligned
    with executable runtime
  - `app_search` runtime consumes frozen filters, latest/relevance sort,
    page/pageSize, and internal `nextPageToken`
  - retrieval routing is centralized in a deterministic policy shared by
    taskGraph projection, retrieval design, and runtime auto-injection
- Residue:
  - legacy `search` tool still exists outside the typed mainline and remains an M5 residue item

### M3
- Status: accepted
- Landed:
  - `IntentTaskCompiler`
  - `TaskScheduler`
  - `UnderstandPhase` emits typed `UnderstandingResult` / `TaskGraph`
  - `BootstrapPhase` now seeds `SystemContextEnvelope` and previous typed state for continuity
  - `AgentExecutionState` no longer stores `searchPlans`; retrieval plans are
    carried by `taskGraph` and projected to legacy search arguments only at
    tool/runtime boundaries.
- Residue:
  - `searchPlans` is still projected for replay/diagnostics compatibility outside the typed execution path

### M4
- Status: accepted
- Landed:
  - execution/finalize/provider/display projection tests are green on the typed mainline
  - UI/provider paths consume canonical persisted assistant turns
- Residue:
  - replay and transcript compaction still carry projected `planView` / `searchPlans`

## M5 Local Closure Scope
### Closed in this session
- typed mainline fields are now persisted through finalize:
  - `systemContextEnvelope`
  - `understandingResult`
  - `taskGraph`
  - `orchestratorState`
  - `turnSynthesisState`
- typed mainline fields now have persisted resolvers in:
  - `lib/assistant/protocol/persisted_assistant_turn.dart`
- UI transcript extra fields now preserve these typed fields in:
  - `lib/ui/assistant/providers/assistant_conversation_controller.dart`
- regression coverage added in:
  - `test/assistant/finalize_runner_test.dart`
  - `test/assistant/orchestration_phase_owner_test.dart`
  - `test/assistant/understand_phase_test.dart`
  - `test/ui/assistant/providers/assistant_conversation_controller_test.dart`
- `local_context` has been removed from:
  - tool implementation files
  - skill assets and prompt snippets
  - direct local-context unit tests
- `AgentExecutionState` no longer carries `conversationStateDecision` or
  `searchPlans`; typed `orchestratorState`, `turnSynthesisState`, and `taskGraph`
  are the runtime state fields.

### Live-provider note
- live-provider closure remains separate from the local closure pass.
- The search audit live slice now has one same-pass proof:
  `flutter test test/assistant/minimax_live_weather_fortune_test.dart --dart-define=LIVE_TEST=true`.
  That proof covers the previously failing final `understandingSnapshot`
  projection path for weather.

## Required Legacy Residue List
The following residue is still real and should not be hidden:
- `lib/assistant/orchestration/phases/understand_phase.dart`
  - typed state is the active execution path
- `lib/assistant/orchestration/state/execution_phase_snapshot.dart`
  - success snapshot carries `UnderstandingResult`, `TaskGraph`, and projected `searchPlans`
- `lib/assistant/protocol/recent_dialogue_rounds.dart`
  - compact history stores typed `planView`

## Local Validation Target
- `flutter test test/assistant/assistant_contracts_roundtrip_test.dart`
- `flutter test test/assistant/finalize_runner_test.dart`
- `flutter test test/ui/assistant/providers/assistant_conversation_controller_test.dart`
- `flutter test test/assistant/understand_phase_test.dart`
- `flutter test test/assistant/orchestration_phase_owner_test.dart`

Optional additional local validation:
- `flutter test test/assistant/full_phase_pipeline_test.dart`

## Live Provider Closure
### Separate scope
Live provider closure remains tracked by:
- `test/assistant/minimax_live_weather_fortune_test.dart`

### Current blocker
- none for the weather live slice in this verification pass
- broader live closure can still be blocked by future credential, account, or
  network availability and should remain classified separately from local code
  closure when those external conditions fail

## M6 Entry Assessment
Current M6 entry decision:
- local centralized verification may proceed
- full M6 final closure is gated on the M5 local validation matrix and live-provider blocker classification

Required before claiming M6 completion:
- run or explicitly block the local validation target commands listed above
- verify typed mainline fields survive finalize, persistence, reload, and UI/provider projection
- keep live provider closure separate from local verification unless valid credentials and a successful non-degraded provider response are available
