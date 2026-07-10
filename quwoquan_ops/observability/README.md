# Observability output contract

Runtime observability has three durable signal families: logs, metrics, and
trace links. Local environment runs write them under
`.qwq_output/env/<env>/observability/<runId>/`; data workflow runs write them
under `.qwq_output/data/observability/<runId>/`. Online environments should
attach the same context through collector labels and the run `manifest.json`.

## Run layout

```text
.qwq_output/env/<env>/observability/<runId>/
  manifest.json
  logs/
  metrics/
  traces/
  attachments/

.qwq_output/data/observability/<runId>/
  manifest.json
  logs/
  metrics/
  traces/
  attachments/
```

`manifest.json` owns run context: `env`, `runId`, release identifiers, git SHA
when available, and `contractVersion`. Log lines must not repeat those fields.

## Log kinds

Only these log file names are allowed:

- `deploy.log` for CI/CD and stackctl steps.
- `runtime.log` for service lifecycle or internal events.
- `access.log` for HTTP, RPC, MQ, and app request/access records.
- `event.log` for app or data workflow events.
- `exception.log` for failures and exceptions.
- `audit.log` for operator or privileged actions.

Each record is comma-delimited text, not JSONL. The first two fields are always
`ts,level`; the final field is always `msg`. Any field that may contain commas,
free text, attributes, or stack text must be appended to `msg`, so parsers can
split only the fixed prefix and keep the rest as the message.

Stack traces and multi-line messages are represented as continuation lines that
start with whitespace. A new record must start with an ISO timestamp followed by
`,DEBUG|INFO|WARN|ERROR,`.

Field order:

- `deploy.log`: `ts,level,step,result,msg`
- `runtime.log`: `ts,level,event,result,req,trace,msg`
- `access.log`: `ts,level,method,route,status,durMs,req,trace,msg`
- `event.log`: `ts,level,event,result,req,trace,msg`
- `exception.log`: `ts,level,err,req,trace,msg`
- `audit.log`: `ts,level,action,target,result,msg`

Forbidden repeated fields: `schemaVersion`, `signal`, `logKind`, `env`,
`sourceType`, `service`, `component`, `instanceId`, `runId`, `releaseId`,
`dataReleaseId`, `sessionId`, `timestamp`, `severity`, `message`, `requestId`,
`traceId`, and `spanId`.

## Metrics and traces

Operational statistics are metrics, not logs. Snapshots belong in
`metrics/snapshot.json`; Prometheus text exposition belongs in
`metrics/prometheus.prom`.

Trace output stores only backend links in `traces/links.json`. Full span exports
belong in the trace backend.

## Artifacts boundary

`.qwq_output/env/<env>/runs/`, `.qwq_output/env/repo/runs/`, and
`.qwq_output/data/runs/` are report/evidence roots, not observability sinks.
Run report directories may only keep `report.json`, `summary.json`,
`summary.md`, and `links.json`. Raw stdout/stderr, logs, trace dumps, and
ad-hoc statistics belong under the matching `observability/<runId>/` directory
or the external observability backend.
