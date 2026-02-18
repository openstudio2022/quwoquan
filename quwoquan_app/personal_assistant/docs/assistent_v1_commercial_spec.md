# Assistent v1 Commercial Spec

## Position

`assistent v1` is the external-ready release line for personal assistant capabilities in `quwoquan_app`.
All public APIs remain under `/v1/*` and core public domain naming follows `assistent*`.

## Architecture

- `AssistentApiGateway` provides release-grade HTTP/SSE APIs.
- `AssistantGateway` remains the runtime orchestration core.
- `AssistentProviderRegistry` manages LLM/search/embedding provider metadata.
- `AssistentCostLedger` records run-level token and cost estimates.
- `AssistentAuthAcl` and `AssistentAuditLogger` enforce access and traceability.
- `AssistentAdapterRuntime` provides channel adapter SPI runtime.

## Release Gate

- API correctness: all endpoints served via `/v1/assistent/*`.
- Security: token auth + ACL checks on invoke/run routes.
- Observability: `runId`/`traceId` returned in all run/invoke responses.
- Cost: every run writes a cost ledger entry.
- Channel: App and Feishu/OpenClaw integration path available through adapter runtime.

## Non-goals

- No v2 endpoint exposure.
- No forced migration of existing internal `assistant*` runtime symbols.
- No coupling with external platform-specific SDKs inside core engine modules.

