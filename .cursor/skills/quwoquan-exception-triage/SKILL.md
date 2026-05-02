---
name: quwoquan-exception-triage
description: Query Elasticsearch exception telemetry, group fingerprints, produce daily reports, and only attempt automated fixes after a reproducible failing test or replay is available. Use when the user mentions ES, 异常监控, 线上错误, 自动修复, exception triage, or 日报.
---

# Quwoquan Exception Triage

## Workflow

1. Query recent exceptions with the stable scripts, never by scraping Kibana:
   - `python3 scripts/observability/es_cli.py daily-report --env alpha --output json`
   - `python3 scripts/observability/es_cli.py query --request-id <requestId> --output json`
   - `python3 scripts/observability/es_cli.py trace-samples --trace-id <traceId>`
2. Group by the script-provided `fingerprint`. Prioritize `nature=bug`, crashes, panics, contract parsing failures, and repeated `errorCode + failurePoint + stackHash` groups.
3. Link samples back to code using `traceId/requestId`, `operationId + surfaceId/routeId/pageName`, `businessObject/functionModule`, and `entityType/entityId`.
4. Before editing code, prove reproduction with a failing test, smoke command, replay request, or deterministic local script.
5. If reproduction is not available, generate a Markdown daily-report item and stop. Do not guess a fix from logs alone.
6. After a fix, rerun the repro, the targeted tests, and the smallest relevant gate. Only then prepare a PR summary.

## Hard Rules

- Do not auto-fix `transient`, `requiresPermission`, or `requiresUserAction` issues unless they are proven to be mishandled by app/cloud code.
- Do not collect or print raw payloads, tokens, complete headers, precise location, SSID/IP, contacts, or unredacted user content.
- Do not use removed fields as new correlation keys: `currentLogType`, `cloudRequestId`, `journeyId`, generic `spanId/parentSpanId/correlationId`, or `pythonJobId`.
- Automatic PRs must include: exception sample, fingerprint, reproduction command, fix summary, verification command, and residual risk.

## Report Template

```markdown
## Summary
- Fingerprint: `<fingerprint>`
- Error: `<errorCode>` / `<nature>`
- Scope: `<appRuntimeEnv>` `<appVersion>` `<businessObject>/<functionModule>`
- Samples: `<traceId>` `<requestId>`

## Reproduction
<command or "not reproducible yet">

## Decision
<fix attempted / report-only human review>
```
