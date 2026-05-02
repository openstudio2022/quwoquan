# M2 Tool Cutover Inventory

## Purpose
This document is the Milestone 2 evidence artifact for:
- tool taxonomy cutover
- `local_context` removal from the new mainline
- app search/action replacement mapping

## New Mainline Tool Surface
- `app_search`
  - Reads permitted in-app information.
  - Covers chat messages, posts, browsing-history posts, users, and circles.
- `app_action`
  - Executes app and system-app actions through one action surface.
  - Covers opening conversations/posts/pages, sending messages, photo actions,
    sharing, and dialing.
- `web_search` / `web_fetch`
  - External web retrieval fallback.
- `SystemContextEnvelope`
  - Replaces `local_context` for injected device/time/location/permission state.

## Deprecated Tool Surface
`local_context` must not be used by the new mainline.

Known residue categories:
- Tool implementation
  - Status: removed from repo
  - Replacement: `SystemContextEnvelope` injection.
- Tool catalog and permissions
  - `assets/assistant/tools/catalog/tool_catalog.meta.json`
  - `assets/assistant/tools/catalog/tool_permissions.json`
  - Replacement: remove `local_context`; add `app_search` / `app_action`.
- Runtime policy
  - `assets/assistant/config/react_policy.json`
  - Replacement: remove `local_context` tool policy entries.
- Skill docs and allowed tools
  - Skills under `assets/assistant/skills/**` now rely on default injected
    system context instead of `local_context`.
  - Replacement: remove `local_context`; rely on `SystemContextEnvelope` for
    device context, `app_search` for in-app information, and `web_search` for
    web evidence.
- Tests
  - `test/assistant/local_context_*`
  - Status: removed
  - `tool_metadata_contract_test.dart`
  - `tool_registry_contract_test.dart`
  - `skill_standard_contract_test.dart`
  - Replacement: new `app_search` / `app_action` contract and routing tests.
- UI/provider imports
  - `lib/ui/assistant/providers/assistant_conversation_controller.dart`
  - Replacement: remove direct `local_context` registration when runtime
    cutover reaches M3/M5.
- Documentation
  - `assistant/docs/architecture_overview.md`
  - `assistant/docs/skill_development_standard.md`
  - `docs/personal-assistant/**`
  - Replacement: update wording to `SystemContextEnvelope`.

## M2 Acceptance Status
- `app_search` contract: passed.
- `app_action` contract: passed.
- skill/tool routing policy: passed as structured `toolName + toolArgs`.
- runtime acceptance: passed for the typed M2 surface.
- resolved gaps:
  - `app_search` now uses the frozen filter/result schema in both contract and executable runtime tool.
  - `app_search` runtime consumes `filters`, `sort=latest/relevance`, `page`,
    `pageSize`, and `nextPageToken` through the canonical adapter before
    materializing results.
  - `app_action` contract remains aligned with the executable tool entry
  - retrieval selection now uses one deterministic runtime policy:
    app object/content plans route to `app_search`, mixed app+web plans route
    to `search`, and pure external realtime plans route to `web_search`.
- `local_context` runtime deletion: completed for the new mainline; remaining cleanup is deferred to M5 current path deletion.

## Validation Evidence
- `flutter test test/assistant/app_search_contract_test.dart`
- `flutter test test/assistant/app_search_tool_runtime_test.dart`
- `flutter test test/assistant/retrieval_tool_selection_policy_test.dart`
- `flutter test test/assistant/app_action_contract_test.dart`
- `flutter test test/assistant/app_action_tool_runtime_test.dart`
- `flutter test test/assistant/skill_match_policy_test.dart`
- `flutter test test/assistant/intent_task_compiler_test.dart`
- `flutter test test/assistant/tool_registry_contract_test.dart`
- `flutter test test/assistant/tool_metadata_contract_test.dart`
