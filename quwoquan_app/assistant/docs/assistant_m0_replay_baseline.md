# Assistant M0 Replay Baseline

## Purpose

This document freezes the current M0 replay baseline contract for the assistant.
Its job is not to prove world-class answer quality. Its job is to make replay
outcomes reproducible, comparable, and explainable before M1 continues.

## Fixed Corpus

The current corpus is defined in
`integration_test/assistant_manual_replay_test.dart` and includes:

- `yesterday_stock_reason`
- `followup_a_stock_reason`
- `yesterday_a_stock_reason`
- `wednesday_a_stock_reason`
- `tomorrow_weather`
- `cold_start_reload`

The runner accepts:

- `ASSISTANT_REPLAY_CASE_FILTER`
- `ASSISTANT_REPLAY_REPEAT_COUNT`
- legacy compatibility via `ASSISTANT_ENABLE_LEGACY_REPLAY_CASES`

## Baseline Pack Contract

Each case emits one baseline pack with:

- fixed case metadata: `caseId`, `turnShape`, `expectedScope`,
  `expectedTemporalAnchor`, `expectedOutcomeClass`
- repeated attempts with per-turn evidence
- canonical state subset derived from persisted assistant turn fields
- linked run log metadata and replay record payload
- stability verdict across repeated replays
- M1 entry verdict for the case

Canonical state comparison is anchored on:

- canonical persisted assistant turn fields（不含版本字段）
- final answer text / answer blocks
- normalized process timeline
- `understandingSnapshot`
- `retrievalProcessing`
- `answerProcessing`
- journey readiness
- `phaseOneRoutingDiagnostics`
- `queryDesignLines`

## Artifact Exit

Artifacts are emitted through two paths:

- app-side JSON files under the replay artifact writer
- `IntegrationTestWidgetsFlutterBinding.reportData` for host-visible summary

The app-side file path is useful for local inspection during a live run. The
`reportData` summary is the durable CI-facing exit and must include the full pack
payload so a sandbox path disappearing does not erase the verdict.

## Failure Taxonomy

The M0 baseline currently freezes these failure classes:

- `none`
- `degraded_fail_closed`
- `heuristic_fallback_used`
- `tool_progress_as_answer`
- `internal_protocol_leak`
- `generic_fallback_answer`
- `empty_final_answer`
- `missing_query_design`
- `weak_evidence_answered`
- `next_action_not_answer`
- `final_answer_not_ready`
- `timeline_not_canonical`
- `reload_state_lost`
- `exception`

`weak_evidence_answered` and `tool_progress_as_answer` are mandatory signatures
before M1 because both were observed in real user runs.

## Stability Gate

The default M0 gate requires:

- selected cases replayed `3` times
- no degraded or heuristic fallback outcome
- no tool-progress placeholder accepted as final answer
- no internal protocol leak
- reload case restores answer text, canonical process steps, and query design
- repeated runs stay consistent on `outcomeClass`, `nextAction`,
  `finalAnswerReady`, and `queryDesignSignature`

## Current Honest Status

Status: `in_progress`

What is landed:

- fixed corpus and case ids
- pack schema and artifact writer
- run log / replay record linkage
- repeat-run stability calculation
- case-level and corpus-level M1 entry verdicts

What is still intentionally open:

- the baseline test can fail because current product behavior is not yet M1-ready
- at least one real smoke run has already shown that `tomorrow_weather` still
  blocks M1 entry under the new gate

That failure is a valid M0 outcome. It means the baseline is catching current
behavior rather than papering over it.

## M1 Entry

M1 is blocked until all selected M0 cases satisfy:

- baseline pack emitted
- repeat count satisfied
- artifact linkage present
- expected outcome reached
- replay stable across repeated runs

Only after that should M1 resume work on investigation planning, evidence pack
quality, and stronger synthesis behavior.
