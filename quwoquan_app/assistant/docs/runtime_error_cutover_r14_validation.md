# Runtime Error Cutover R14 Validation

## Scope

- R15 metadata recovery semantics: metadata no longer defines `recovery policy`, `recoveryAction`, or `recovery_after_seconds` as error facts.
- R16 guard hardening: cutover guard blocks current metadata retry fields, generated cloud `recoveryAction`, UI primary error state stringification, assistant `result.runtimeFailure` propagation, unregistered Ops runtime codes, and Ops `.test-dist` artifacts.
- R11 assistant runtime: failed `AssistantToolResult`, `AssistantModelOutput`, and `ReactRuntimeResult` expose typed runtime failure for policy decisions.
- R12 UI/provider errors: key non-assistant providers and error surfaces use structured runtime display mapping rather than raw exception strings.
- R13 Ops: test script compiles API, runtime barrel, and page runtime error usage under NodeNext.

## Validation

- `dart tools/runtime_error_codegen/bin/generate_runtime_errors.dart --check`
- `dart tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`
- `flutter test test/assistant/assistant_tool_result_runtime_failure_test.dart test/assistant/assistant_runtime_failure_mapper_test.dart test/assistant/assistant_run_e2e_test.dart test/cloud/content/post/contract/post_error_code_contract_test.dart test/cloud/chat/contract/chat_error_code_contract_test.dart test/cloud/user/contract/user_error_code_contract_test.dart test/cloud/rtc/rtc_errors_test.dart`
- `npm test` in `apps/ops-portal`
- `go test ./runtime/errors ./runtime/governance ./runtime/sync` in `quwoquan_service`
- `go test ./tests` in `quwoquan_service/services/entity-service`
- `go test ./tests -run 'TestErrorCode_'` in `quwoquan_service/services/user-service`

## Known Validation Limits

- Full `go test ./tests` for `user-service` was not used as the R14 pass/fail signal because the local embedded Postgres data directory contained pre-existing persona rows and caused duplicate-key failures unrelated to the runtime error cutover. The focused user-service error contract tests passed.
- Live assistant replay was not executed in this pass; the validated coverage is static contract, unit/contract, local e2e, Go service, and Ops runtime/API/page compilation.
