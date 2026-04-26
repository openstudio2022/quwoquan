# Runtime Error Cutover R21 Validation

## Completed Scope

- R17: Removed legacy recovery naming from service governance docs, React policy config/code, assistant assets, and web search error classification.
- R18: Assistant tool implementation failures now carry explicit `RuntimeFailure` via `assistantToolRuntimeFailure`; `effectiveRuntimeFailure` remains only as a defensive boundary fallback.
- R19: Ops domain pages use NodeNext-explicit runtime/API imports, and `npm test` compiles all Ops pages that participate in the runtime error surface.
- R20: Cutover guard now blocks legacy retry naming, text-based assistant session filtering, assistant tool failures without `RuntimeFailure`, Ops extensionless runtime/API imports, Ops `.test-dist`, and existing runtime contract regressions.

## Validation Commands

- `dart tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check`
- `dart tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`
- `flutter test test/assistant/assistant_tool_result_runtime_failure_test.dart test/assistant/assistant_runtime_failure_mapper_test.dart test/assistant/tool_registry_contract_test.dart test/assistant/assistant_run_e2e_test.dart test/cloud/content/post/contract/post_error_code_contract_test.dart test/cloud/chat/contract/chat_error_code_contract_test.dart test/cloud/user/contract/user_error_code_contract_test.dart test/cloud/rtc/rtc_errors_test.dart`
- `flutter test test/assistant/web_fetch_tool_test.dart test/assistant/web_fetch_tool_contract_test.dart test/assistant/search_tool_test.dart test/assistant/app_action_tool_runtime_test.dart test/assistant/app_search_tool_runtime_test.dart`
- `npm test && npm run build` in `apps/ops-portal`
- `go test ./runtime/errors ./runtime/governance ./runtime/sync` in `quwoquan_service`
- `go test ./tests` in `quwoquan_service/services/entity-service`
- `go test ./tests -run 'TestErrorCode_'` in `quwoquan_service/services/user-service`

## Verification Notes

- `.test-dist` is removed after Ops tests and is blocked by the cutover guard.
- Full user-service `go test ./tests` remains unsuitable as a runtime-error cutover signal in this workspace because the local embedded Postgres directory has previously shown persisted persona rows that trigger unrelated uniqueness failures. The runtime error contract subset passed.
- Live assistant replay was not executed in this pass; coverage is contract, static guard, Flutter unit/e2e, Ops compile/runtime tests, and Go runtime/service error contract tests.
