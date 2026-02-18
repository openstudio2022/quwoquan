# Assistent v1 Release Runbook

## 1. Pre-check

- Verify env vars:
  - `PERSONAL_ASSISTANT_GATEWAY_TOKEN`
  - `PERSONAL_ASSISTANT_OPENCLAW_BASE_URL`
  - provider keys for web search/model routing
  - `ASSISTENT_FEISHU_SIGN_MODE`, `ASSISTENT_FEISHU_SIGN_SECRET`
  - `ASSISTENT_OPENCLAW_SIGN_MODE`, `ASSISTENT_OPENCLAW_SIGN_SECRET`
  - `ASSISTENT_ALERT_WEBHOOK_URL`
  - `ASSISTENT_ALERT_FEISHU_WEBHOOK`
  - `ASSISTENT_ALERT_SUPPRESS_SECONDS`
  - `ASSISTENT_ALERT_AUTO_DISABLE_MINUTES`
- Ensure skill assets are bundled under `assets/personal_assistant/skills/`.

## 2. Start Gateways

- Runtime gateway: existing `AssistantHttpGateway` (`/v1/*`)
- Commercial API gateway: `AssistentApiGateway` (`/v1/assistent/*`)

## 3. Functional Smoke

1. `GET /v1/assistent/providers`
2. `GET /v1/assistent/skills?channel=app`
3. `POST /v1/assistent/runs`
4. `POST /v1/assistent/runs/stream`
5. `GET /v1/assistent/costs`
6. `GET /v1/assistent/alerts`
7. Run one-shot canary script:
   - `personal_assistant/scripts/assistent_canary_check.sh`
8. Run alert routing test script:
   - `personal_assistant/scripts/assistent_alert_route_test.sh`
9. If provider is temporarily disabled by critical alerts:
   - `POST /v1/assistent/providers/{providerId}/recover`

## 4. Channel Smoke

- Feishu route:
  - invoke `knowledge_qa`
  - verify response contains `runId` and `traceId`
- OpenClaw route:
  - invoke remote skill via bridge
  - verify fallback path

## 5. Release Gate

- No analyzer errors.
- Auth/ACL check enabled.
- Cost ledger writes for every run.
- Audit log records available.
- SLO snapshot healthy on smoke load.

## 6. Rollback

- Stop `AssistentApiGateway`.
- Route traffic back to existing `/v1` assistant gateway.
- Keep audit and cost logs for postmortem.

