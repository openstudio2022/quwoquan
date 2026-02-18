# Assistent v1 Commercial Acceptance Checklist

## Build and Startup

- [ ] App compiles with `PERSONAL_ASSISTENT_ENABLE_API=true`.
- [ ] `AssistentApiGateway` starts on port `19191`.
- [ ] `GET /v1/assistent/adapters` returns at least `feishu` and `openclaw`.

## Security and Governance

- [ ] Bearer token validation works when `PERSONAL_ASSISTANT_GATEWAY_TOKEN` is set.
- [ ] ACL denies malformed actor/resource/action requests.
- [ ] Audit logs are written for run and invoke flows.

## Core Commercial APIs

- [ ] `GET /v1/assistent/providers` returns LLM/search provider metadata.
- [ ] `GET /v1/assistent/skills?channel=app` returns governed skills.
- [ ] `POST /v1/assistent/skills/invoke` returns `runId/traceId` and result envelope.
- [ ] `POST /v1/assistent/runs` returns `runId/traceId/finalText/degraded/errorCode`.
- [ ] `POST /v1/assistent/runs/stream` streams trace events and final payload.
- [ ] `GET /v1/assistent/sessions` returns persisted session summaries.

## Channel Adapter Serviceability

- [ ] `POST /v1/assistent/channels/feishu` ingests webhook payload and dispatches response envelope.
- [ ] `POST /v1/assistent/channels/openclaw` ingests OpenClaw payload and dispatches response envelope.
- [ ] Adapter verification rejects invalid signatures/tokens when configured.

## Cost and Observability

- [ ] Run execution creates `AssistentCostLedger` records.
- [ ] `GET /v1/assistent/costs` returns summary and recent records.
- [ ] All run/invoke responses include `runId` and `traceId`.

## End-to-End Scenarios

- [ ] App text QA flow succeeds with knowledge answer.
- [ ] Feishu webhook text -> Assistent run -> adapter dispatch flow succeeds.
- [ ] OpenClaw ingress -> Assistent run -> dispatch flow succeeds.
- [ ] Provider degradation path still produces safe fallback response.

