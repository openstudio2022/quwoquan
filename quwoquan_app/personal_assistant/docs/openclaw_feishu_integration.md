# Personal Assistant Integration Guide

## Purpose

This document describes how `quwoquan_app` exposes `personal_assistant` capabilities
to OpenClaw, Feishu, and other external channels through a unified API layer.

## Endpoints

- `GET /v1/skills`: list assistant skill metadata
- `POST /v1/skills/invoke`: execute one skill by id
- `POST /v1/run`: run one ReAct session turn
- `POST /v1/run/stream`: run one turn with SSE trace output
- `GET /v1/sessions`: list persisted sessions
- `GET /v1/sessions/:sessionId`: query one session detail/summary
- `GET /v1/assistent/adapters`: list commercial adapter plugins
- `GET /v1/assistent/alerts`: list recent SLO alerts
- `POST /v1/assistent/channels/{adapterId}`: adapter ingress (feishu/openclaw)
- `POST /v1/assistent/runs`: commercial run API
- `POST /v1/assistent/runs/stream`: commercial streaming run API

## Authentication

- Optional bearer token gate:
  - Set `PERSONAL_ASSISTANT_GATEWAY_TOKEN`
  - Send `Authorization: Bearer <token>`

## Rate limit and audit

- Built-in baseline rate limit: 30 requests/minute per token/IP
- If limited, gateway returns:
  - HTTP `429`
  - body: `{ "error": "rate_limited", "message": "too many requests" }`
- Gateway prints audit logs for `run` / `skills` / `invokeSkill` requests.
- Commercial gateway also writes structured audit logs (`AssistentAuditLogger`) and cost entries (`AssistentCostLedger`).

## Startup

- Enable commercial gateway by environment compile flag:
  - `PERSONAL_ASSISTENT_ENABLE_API=true`
- Default commercial gateway port: `19191`
- Signature strategy config (adapter verify):
  - `ASSISTENT_FEISHU_SIGN_MODE=none|token|hmac_sha256`
  - `ASSISTENT_FEISHU_SIGN_SECRET=...`
  - `ASSISTENT_OPENCLAW_SIGN_MODE=none|token|hmac_sha256`
  - `ASSISTENT_OPENCLAW_SIGN_SECRET=...`

## OpenClaw Integration Pattern

1. OpenClaw syncs available skills from `GET /v1/skills`.
2. OpenClaw registers remote tools using returned skill metadata.
3. When user requests a capability, OpenClaw calls `POST /v1/skills/invoke`.
4. OpenClaw renders `message`/`data` in channel UI.
5. OpenClaw can subscribe to `POST /v1/run/stream` to render live trace step-by-step.

## Feishu Integration Pattern

1. Feishu bot receives user command.
2. Command router calls OpenClaw (or directly this gateway).
3. Gateway executes skill and returns normalized JSON result.
4. Feishu bot sends back text/card to current conversation.

## Example: list skills

```bash
curl -s "http://127.0.0.1:18181/v1/skills"
```

## Example: invoke one skill

```bash
curl -s -X POST "http://127.0.0.1:18181/v1/skills/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "web.quick_search",
    "channel": "feishu",
    "deviceProfile": "mobile",
    "arguments": {
      "toolName": "web_search",
      "toolArgs": { "query": "Flutter AppIntents plugin" }
    }
  }'
```

## Example: invoke commercial knowledge_qa (recommended)

```bash
curl -s -X POST "http://127.0.0.1:18181/v1/skills/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "knowledge_qa",
    "channel": "feishu",
    "deviceProfile": "mobile",
    "arguments": {
      "toolArgs": {
        "query": "请给出杭州周末天气与出行建议",
        "provider": "perplexity",
        "backupProviders": ["brave", "openclaw_proxy"],
        "maxEvidence": 6
      }
    }
  }'
```

## Example: run one turn with stream

```bash
curl -N -X POST "http://127.0.0.1:18181/v1/run/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "assistant-stream",
    "deviceProfile": "pc",
    "messages": [
      { "role": "user", "content": "帮我查杭州本周天气并给出出行建议" }
    ]
  }'
```

## Example: run one turn

```bash
curl -s -X POST "http://127.0.0.1:18181/v1/run" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "assistant",
    "deviceProfile": "mobile",
    "messages": [
      { "role": "user", "content": "帮我搜索 Flutter AppIntent 方案" }
    ]
  }'
```

## Runnable scripts

- `personal_assistant/scripts/list_skills.sh`
- `personal_assistant/scripts/feishu_openclaw_voice_demo.sh`
- `personal_assistant/scripts/run_chat_turn.sh`
