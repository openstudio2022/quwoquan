# M6 Centralized Verification Report

## Scope
This report records the M6 verification run for the typed assistant mainline cutover.

Hard requirements under verification:
- no `local_context` tool exposure
- typed contracts survive finalize, persistence, reload, and UI projection
- simulator weather and stock replay are executed and honestly classified
- legacy/weak/text-heuristic residues are not hidden

## Local Contract And UI Matrix
Status: pass.

Command:

```sh
flutter test test/assistant/app_search_contract_test.dart test/assistant/app_search_tool_runtime_test.dart test/assistant/app_action_contract_test.dart test/assistant/app_action_tool_runtime_test.dart test/assistant/skill_match_policy_test.dart test/assistant/intent_task_compiler_test.dart test/assistant/task_scheduler_test.dart test/assistant/tool_registry_contract_test.dart test/assistant/tool_metadata_contract_test.dart test/assistant/understand_phase_test.dart test/assistant/orchestration_phase_owner_test.dart test/assistant/assistant_contracts_roundtrip_test.dart test/assistant/assistant_pipeline_precomputed_contracts_test.dart test/assistant/assistant_typed_mainline_architecture_guard_test.dart test/assistant/finalize_runner_test.dart test/assistant/assistant_boundary_outcome_test.dart test/assistant/assistant_run_response_runtime_failure_test.dart test/assistant/assistant_runtime_failure_mapper_test.dart test/assistant/assistant_tool_result_runtime_failure_test.dart test/assistant/assistant_display_state_projection_test.dart test/assistant/process_timeline_projection_test.dart test/ui/assistant/providers/assistant_conversation_controller_test.dart
```

Result:
- all tests passed
- verified M2 tool contracts, executable runtime tools, routing, metadata contract, and scheduler/compiler
- verified M3 typed bootstrap/understand continuity, `SystemContextEnvelope` propagation, and architecture guards
- verified M4/M5 finalize persistence, runtime failure projection, display/process projection, and UI/provider reload path
- total passing cases in this centralized local run: 133

## Mainline Regression Matrix
Status: pass for current local matrix.

Command:

```sh
flutter test test/assistant/understand_phase_test.dart test/assistant/orchestration_phase_owner_test.dart test/assistant/assistant_typed_mainline_architecture_guard_test.dart
```

Result:
- all tests passed
- `UnderstandPhase` now carries previous typed `UnderstandingResult` / `TaskGraph` into continuity
- `BootstrapPhase` now seeds `SystemContextEnvelope` into owner state and precomputed bootstrap payloads
- architecture guard still blocks reintroduction of deleted legacy decision bridges

M6 interpretation:
- the current typed mainline regression matrix is green locally
- remaining residue is limited to explicitly-audited compatibility DTO boundaries, not a failing mainline regression

## Simulator Replay
Status: pass in this verification pass.

Devices:
- iPhone 15 Pro Max simulator, iOS 17.2
- iPad Pro (12.9-inch) (6th generation), iOS 17.2

### Weather
Command:

```sh
flutter test integration_test/assistant_manual_replay_test.dart -d 22945797-42C9-4CF5-BEA1-B1C873B64904 --plain-name "Assistant M0 replay baseline" --dart-define=ASSISTANT_REPLAY_CASE_FILTER=tomorrow_weather --dart-define=ASSISTANT_REPLAY_REPEAT_COUNT=1
flutter test integration_test/assistant_manual_replay_test.dart -d EAF3A223-E742-433D-B116-A152DCC7FF84 --plain-name "Assistant M0 replay baseline" --dart-define=ASSISTANT_REPLAY_CASE_FILTER=yesterday_stock_reason,tomorrow_weather --dart-define=ASSISTANT_REPLAY_REPEAT_COUNT=1
```

Result:
- pass on both iPhone 15 Pro Max and iPad Pro 12.9 simulators
- the weather replay no longer stops at `degraded_fail_closed`
- the replay now exits with `nextAction=answer` and `finalAnswerReady=true`

Observed:
- `understandingResult.intents[]` carried `weather_query`
- `taskGraph.tasks[]` carried the weather task and explicit `2026-04-27` / `深圳` query
- location is now validated through structured `entityRefs` instead of removed `resolvedGeoScope`
- final turn produced `matchedExpected=true`, `degraded=false`, `nextAction=answer`, `finalAnswerReady=true`
- final mode was `bounded_answer`, but the replay outcome was `answer_ready` because the typed answer gate was ready

Classification:
- earlier failure was partly a system-context injection bug and partly legacy replay validation that still required removed geography fields
- current simulator gate is correct for the typed mainline

### Stock
Command:

```sh
flutter test integration_test/assistant_manual_replay_test.dart -d EAF3A223-E742-433D-B116-A152DCC7FF84 --plain-name "Assistant M0 replay baseline" --dart-define=ASSISTANT_REPLAY_CASE_FILTER=yesterday_stock_reason,tomorrow_weather --dart-define=ASSISTANT_REPLAY_REPEAT_COUNT=1
```

Result:
- pass on iPad Pro 12.9 simulator in the same verification pass

Observed:
- user-visible answer was generated
- `matchedExpected=true`
- `degraded=false`
- `nextAction=answer`
- `finalAnswerReady=true`
- final mode was `bounded_answer`
- `outcomeClass=answer_ready`

Classification:
- simulator journey can answer stock query
- earlier failure was caused by old text/answer-mode gate semantics, not by runtime inability to answer

## Fixes Landed During M6
- Completed centralized local verification for M2-M5 typed mainline paths.
- Restored typed system-context propagation through bootstrap, understand, precomputed bootstrap payloads, finalize, persistence, and UI projection.
- The model-facing tool surface still does not expose `local_context`.
- `BootstrapPhase` now rehydrates previous typed `understandingResult` / `taskGraph` for continuity when only prior `planView` is available.
- `UnderstandPhase` now serializes previous typed state into planner continuity variables instead of sending empty placeholders.
- `synthesizer.final_answer` output is now treated as invalid when it still returns `tool_call` / progress instead of a final answer envelope, and the repair path is triggered before fail-closed replay gating.
- owner-level regression coverage now locks the repaired path in `test/assistant/orchestration_phase_owner_test.dart`.
- retrieval broker / `search` / `web_search` boundaries now consume a dedicated retrieval-plan wire DTO, so `SearchPlanItem` no longer leaks across tool/runtime boundaries.
- `app_search` runtime now consumes frozen filters, latest/relevance sort,
  page/pageSize, and internal `nextPageToken`; result materialization remains
  limited to permitted returned hits.
- retrieval tool selection is centralized in a deterministic policy shared by
  taskGraph projection, retrieval design, and runtime auto-injection.
- final response materialization/finalize now keeps a carried
  `understandingSnapshot` when the final answer does not rewrite one.

## Remaining Blockers
- No blocker remains for the weather live-provider slice in this verification pass.
- Future live runs can still be blocked by credentials, provider account state,
  or network availability; those should be classified separately when they occur.

## Live Provider Verification
Status: pass in this verification pass.

Command:

```sh
flutter test test/assistant/minimax_live_weather_fortune_test.dart --dart-define=LIVE_TEST=true
```

Result:
- pass
- non-degraded live weather answer
- final `structuredResponse.understandingSnapshot.userFacingSummary` remains
  present and includes the requested location

## M6 Verdict
M6 is complete as a centralized verification milestone for the current search
audit scope, with explicit external-risk classification.

Accepted:
- typed contract, orchestration, finalize, persistence, reload, and UI/provider local matrix
- centralized regression proof for the typed mainline
- same-pass simulator replay proof on iPhone and iPad 17.2 simulators
- same-pass live-provider weather proof
- explicit classification of replay/diagnostic residue and separate future live-provider risk

