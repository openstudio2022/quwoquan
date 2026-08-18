---
name: incident-inspection
description: Read-only inspection of production exception telemetry - query Elasticsearch, group fingerprints, produce redacted daily reports, triage priority and owner, and judge reproduction eligibility before any fix. Make sure to use this skill whenever the user mentions ES, 异常监控, 线上错误, 线上异常, 巡检, 日报, exception triage, fingerprint, traceId, or requestId, even without an explicit command.
metadata:
  kind: workflow
---

# incident-inspection

线上异常的只读巡检：查询、分组定级、复现资格判断。**本工作流不修改代码**；
取得可复现证据后只交接 `dev`。五段执行契约见根 `AGENTS.md`。

与 observability 评审角色的区别：本工作流处理**运行中异常**；
observability checklist 只评审某次变更的指标、日志、告警和追踪完整性。

## 触发

无斜杠命令，自然语言自动触发：线上异常巡检、ES 日报、fingerprint 分组、
指定 trace/request 调查、复现资格判断。

## 输入

- 环境与时间窗；或 traceId / requestId / fingerprint / 失败样本。
- ES 访问凭证（缺失时按阻塞如实报告，不猜数据）。

## 角色

见 [references/roles/](references/roles/)，三个只读角色接力：

- [telemetry-inspector](references/roles/telemetry-inspector.md)：稳定 CLI 查询、脱敏与聚类。
- [incident-triager](references/roles/incident-triager.md)：定级并关联 owner。
- [reproduction-analyst](references/roles/reproduction-analyst.md)：构造红测 / replay，判复现资格。

## 执行

自由度：低（查询工具与判定顺序固定）。

1. 用稳定脚本查询，禁止爬 Kibana：
   - `python3 quwoquan_service/scripts/tools/observability/es_cli.py daily-report --env alpha --output json`
   - `python3 quwoquan_service/scripts/tools/observability/es_cli.py query --request-id <requestId> --output json`
   - `python3 quwoquan_service/scripts/tools/observability/es_cli.py trace-samples --trace-id <traceId>`
2. 按脚本给出的 `fingerprint` 分组；优先 `nature=bug`、crash、panic、契约解析失败、
   重复的 `errorCode + failurePoint + stackHash` 组。
3. 用 `traceId/requestId`、`operationId + surfaceId/routeId/pageName`、
   `businessObject/functionModule`、`entityType/entityId` 把样本回链到代码与 owner。
4. 复现资格判断：能构造失败测试、smoke 命令、replay 请求或确定性本地脚本才算可复现；
   不可复现时生成日报条目并停止，**不从日志猜修复**。

## 交付件

**脱敏巡检报告**：fingerprint 优先级、owner、样本回链、复现证据与
`report-only / handoff-dev` 结论。逐 fingerprint 模板：

```markdown
## Summary
- Fingerprint: `<fingerprint>`
- Error: `<errorCode>` / `<nature>`
- Scope: `<appRuntimeEnv>` `<appVersion>` `<businessObject>/<functionModule>`
- Samples: `<traceId>` `<requestId>`

## Reproduction
<command or "not reproducible yet">

## Decision
<handoff-dev / report-only>
```

送审前自检：无原始 payload、token、完整 header、精确位置、SSID/IP、联系人或未脱敏
用户内容；每条结论有样本证据。

## 内置评审

- POST 调 `review`（workflow=`incident-inspection`，segment=POST，
  deliverable=`inspection-report`），角色 observability + ops，
  校验脱敏完整、定级有据、复现结论不越权。

## 失败与停止

- 全程只读；[MUST NOT] 修改代码或配置。
- [MUST NOT] 处理未证明为 app/cloud 代码缺陷的 `transient`、`requiresPermission`、
  `requiresUserAction`。
- [MUST NOT] 使用退役字段作关联键：`currentLogType`、`cloudRequestId`、`journeyId`、
  泛用 `spanId/parentSpanId/correlationId`、`pythonJobId`。
- 凭证或数据缺失按阻塞报告，不估算、不编造样本。

## HANDOFF

- **产出物**：脱敏巡检报告。
- **未决项去向**：不可复现的 fingerprint 保留 report-only 状态与继续观察条件。
- **唯一合法下游**：可复现的代码缺陷交接 `dev`（附异常样本、fingerprint、复现命令）；
  其余报告给用户结束。
- **证据链**：es_cli 查询输出、复现命令与结果。
