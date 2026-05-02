# M1 Contract Cutover Inventory

## Review Rebaseline
This inventory was refreshed after the specification review.

Current status:
- `M1` is **accepted for contract-layer cutover**
- reason: the implemented M1 contracts now align with the frozen simplified spec; runtime mainline deletion remains scheduled for M3/M5

The following review conclusions supersede earlier M1 assumptions:
- remove `local_context` tool completely from the new mainline
- keep only `app_search`; do not keep `app_read` in the current milestone
- merge `device_action` into unified `app_action`
- simplify `SystemLocationContext` from `country/region/city` into map-friendly administrative levels
- remove premature optimization/control fields from `UnderstandingResult`, such as complexity/planning classifications
- simplify `TaskGraph` so tasks carry `intentId + toolName + toolArgs + status + output`, not task taxonomy or graph metadata
- move user-facing clarification / answer / user-input waiting into orchestrator or synthesis interaction directives, not task definitions
- simplify orchestrator state into task lists, using `pendingTaskBatches` to express serial batches with intra-batch parallel execution

## Purpose
This document is the Milestone 1 evidence artifact for:
- current mainline deletion targets
- weak-type inventory
- typed replacement mapping

It exists so Milestone 1 can be validated without ambiguity.

## Current Mainline Deletion Targets
### Contracts and state objects
- `lib/assistant/contracts/understanding_result_contract.dart`
  - Status: active main orchestration path
  - Companion: `lib/assistant/contracts/task_graph_contract.dart`
- `lib/assistant/contracts/search_plan_contract.dart`
  - Status: delete from main orchestration path
  - Replacement: `lib/assistant/contracts/task_graph_contract.dart`
- `local_context` tool contract and all routing references
  - Status: delete from tool mainline
  - Replacement: `SystemContextEnvelope` system injection

### Runtime entry points
- `UnderstandPhase` precomputed path using `precomputedUnderstandingResult` / `precomputedTaskGraph`
  - Status: active typed mainline
  - Replacement: `UnderstandingResult` + `TaskGraph`
- `AgentExecutionState.understandingResult`
  - Status: active typed state
  - Companion: `AgentExecutionState.taskGraph`
- `AgentExecutionState.searchPlans`
  - Status: deprecated, scheduled for deletion
  - Replacement: `AgentExecutionState.taskGraph`
- `AgentExecutionState.conversationStateDecision`
  - Status: deprecated, scheduled for deletion
  - Replacement: `AgentExecutionState.orchestratorState`

## Weak-Type Inventory
### Allowed temporary serde boundaries
- `AssistantBootstrapContext.recentDialogueRounds`
  - Current type: `List<Map<String, dynamic>>`
  - Reason kept temporarily: persistence/history serde boundary
  - Migration direction: typed history/session wire model
- `AssistantBootstrapContext.continuityOverrideSlots`
  - Current type: `Map<String, dynamic>`
  - Reason kept temporarily: model serde boundary
  - Migration direction: typed continuity override contract
- `AssistantExecutionPreparation.fromJson/toJson`
  - Current type: JSON boundary
  - Reason kept temporarily: existing persistence wire
  - Migration direction: typed execution preparation contract if retained

### High-priority weak-type risks
- `UnderstandPhase`
  - Risk: consumes raw `contextScopeHint` maps and old precomputed intent maps
  - Impact: blocks strong-typed understanding mainline
- Bootstrap/session history assembly
  - Risk: raw message maps still flow through internal state
  - Impact: can reintroduce string-key business logic

## Typed Replacement Mapping
- `system context` -> `SystemContextEnvelope`
- `understanding payload` -> `UnderstandingResult`
- `query task list` -> `TaskGraph`
- `turn execution readiness / control plane` -> `ConversationOrchestratorState`
- `answer mode / completion coverage` -> `TurnSynthesisState`

## M1 Completion Criteria
Milestone 1 is not complete unless:
- every deletion target above has a replacement mapping
- every weak-type boundary above has a migration direction
- no new weak-type business protocol is introduced while implementing M1
- implemented contracts also align with the frozen simplified spec:
  - no `TurnComplexityClass`
  - no `PlanningHintType`
  - no `UserResponsePolicy`
  - no `TaskKind`
  - no `TaskExecutionMode`
  - no `app_read`
  - no `device_action`
  - no `dependsOn`
  - no `blockingReason`
  - no `resultRefs`
  - no `graphMeta`
  - no `successCriteria`
  - no `intentPriority`

## M1 Acceptance Result
Current M1 acceptance status:
- contract shape: accepted
- round-trip tests: passed with `flutter test test/assistant/m1_contracts_roundtrip_test.dart`
- runtime cutover: not part of M1 acceptance; remains tracked under M3/M5

M2 status:
- in progress
- contract and routing skeleton exist, but runtime cutover is not accepted yet
- M2 must only introduce `app_search`, `app_action`, and existing `web_search/web_fetch` routing
