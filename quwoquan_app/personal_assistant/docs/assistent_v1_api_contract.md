# Assistent v1 API Contract

Base URL example: `http://127.0.0.1:19191`

## Auth

- Optional bearer token:
  - Env: `PERSONAL_ASSISTANT_GATEWAY_TOKEN`
  - Header: `Authorization: Bearer <token>`

## Endpoints

- `GET /v1/assistent/providers`
- `POST /v1/assistent/providers/{providerId}/recover`
- `GET /v1/assistent/costs`
- `GET /v1/assistent/alerts`
- `GET /v1/assistent/alerts/config`
- `POST /v1/assistent/alerts/test`
- `GET /v1/assistent/skills?channel=app`
- `GET /v1/assistent/sessions`
- `POST /v1/assistent/skills/invoke`
- `POST /v1/assistent/runs`
- `POST /v1/assistent/runs/stream` (SSE)

## POST /v1/assistent/runs Request

```json
{
  "sessionId": "assistant",
  "userId": "u1",
  "channel": "app",
  "traceId": "trace_123",
  "deviceProfile": "mobile",
  "maxIterations": 8,
  "messages": [
    {"role": "user", "content": "请帮我做杭州周末出行规划"}
  ]
}
```

## POST /v1/assistent/runs Response

```json
{
  "runId": "1730000000000_assistant",
  "traceId": "trace_123",
  "finalText": "....",
  "degraded": false,
  "errorCode": null,
  "traces": []
}
```

## Error Contract

- `401 unauthorized`
- `403 forbidden`
- `404 not_found`
- `500 internal_error`

