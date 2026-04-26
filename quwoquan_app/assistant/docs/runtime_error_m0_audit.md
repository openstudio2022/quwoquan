# Runtime Error M0 Audit

## Scope

This audit freezes the first migration target for the Runtime Failure framework. The shared runtime error fact is `RuntimeFailureBase` with `code`, `origin`, `kind`, `nature`, `location`, and string-only `context.attributes`. Retry, fallback, and UI disruption are recovery policy decisions, not error fact fields.

## Current Entrypoints

| Area | Current entrypoint | Current issue | Migration target |
| --- | --- | --- | --- |
| Assistant run response | `quwoquan_app/lib/assistant/protocol/run_response.dart` | `degraded` and `errorCode` are top-level legacy control fields. | Keep only as transitional view; primary state moves to `AssistantBoundaryOutcome`. |
| Assistant pipeline | `quwoquan_app/lib/assistant/orchestration/pipelines/assistant_pipeline_engine.dart` | Pipeline catches failures and emits scattered degraded/trace state. | Map boundary exits to `RuntimeFailureBase` and aggregate with `AssistantBoundaryOutcome`. |
| Assistant stream/UI | `quwoquan_app/lib/ui/assistant/providers/assistant_conversation_controller.dart` | Stream failure paths collapse to empty assistant messages without a typed failure state. | Surface `AssistantBoundaryOutcome` to projection/UI. |
| Assistant tool schema | `quwoquan_app/lib/assistant/tool/schema/tool_schema.dart` | Tool errors are local and can carry fallback copy semantics. | Tool boundary returns task status plus `RuntimeFailureBase`. |
| App cloud mapper | `quwoquan_app/lib/cloud/runtime/errors/cloud_error_mapper.dart` | Parses only `code` and maps to content-specific enum and `CloudException.message`. | Parse `RuntimeErrorResponse` into `RuntimeFailure`. |
| App cloud exception | `quwoquan_app/lib/cloud/runtime/errors/cloud_exception.dart` | Holds domain enum and message as primary fields. | Become adapter input for `RuntimeFailureMapper`. |
| Cloud runtime errors | `quwoquan_service/runtime/errors/errors.go` | Early migration baseline lacked a unified `location/context` response shape. | Emit runtime error responses with `location` and string-only `context.attributes`. |
| Cloud IO logs | `quwoquan_service/runtime/observability/io_access_log.go` | Logs `errorCode` but not runtime failure `location/context`. | Add runtime failure fields in a later cloud migration. |
| Ops portal | `apps/ops-portal` | No shared runtime error model yet. | Consume generated TypeScript runtime error types. |

## Legacy Fields

The following fields are legacy for control-flow purposes:

- `recovery policy`: recovery policy output, not a public error fact.
- `details`: replaced by string-only `context.attributes`.
- `degraded`: replaced by assistant-specific boundary status.
- `errorCode`: remains a stable code string but is no longer enough on its own.
- `toolError`: replaced by task/tool boundary `RuntimeFailureBase`.
- dynamic debug/message text: logging only; not state-machine input or assistant narrative.

## Migration Classification

| Entrypoint | Mapper | Policy | Outcome |
| --- | --- | --- | --- |
| HTTP/cloud response | `RuntimeFailureMapper<RuntimeErrorResponse>` | App recovery policy | App presenter or assistant boundary |
| Dart exception | `RuntimeFailureMapper<Object>` | App recovery policy | App presenter |
| Assistant phase failure | `AssistantBoundaryErrorMapper` | Assistant recovery policy | `AssistantBoundaryOutcome` |
| Assistant task/tool failure | `AssistantBoundaryErrorMapper` | Assistant recovery policy | `TaskStatus` plus `AssistantBoundaryOutcome` |
| Go `AppError` | Go runtime failure mapper | Cloud recovery policy | HTTP/MQ/log response |
| MQ/async failure | Go runtime failure mapper | Cloud recovery policy | Log, compensate, or surface |

## Required Cutover Order

1. Create contract source and Dart/Go packages.
2. Wire assistant boundaries to the Dart runtime package.
3. Wire assistant UI and replay tests to `AssistantBoundaryOutcome`.
4. Migrate App `CloudErrorMapper` and local runtime errors.
5. Migrate Go runtime errors, middleware, logs, and MQ envelopes.
6. Add TypeScript/Python generated models when management/offline flows need them.

## Acceptance Notes

- Every audited entrypoint has a target: mapper, policy, or assistant boundary outcome.
- No user-facing failure narrative should be generated from code-side strings.
- `context.attributes` is always log/debug context and never business logic input.
