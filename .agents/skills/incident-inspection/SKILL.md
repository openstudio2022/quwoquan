---
name: incident-inspection
description: Read-only inspection of production exception telemetry - query Elasticsearch, group fingerprints, produce redacted daily reports, triage priority and owner, and judge reproduction eligibility before any fix. Make sure to use this skill whenever the user mentions ES, 异常监控, 线上错误, 线上异常, 巡检, 日报, exception triage, fingerprint, traceId, or requestId, even without an explicit command.
metadata:
  kind: workflow
---

# incident-inspection

## 触发与输入

在线上异常、ES 巡检/日报、fingerprint 分组、traceId/requestId 调查或复现资格判断时
使用。输入是环境与时间窗，或明确的 traceId、requestId、fingerprint、失败样本；ES
凭证缺失即阻塞，不猜测数据。

本工作流只读且不修改代码。只有需要独立分工时才读取对应
[roles/](references/roles/)；运行中异常检视不等于对代码变更做 observability Review。

## 执行

只使用稳定 CLI，禁止爬取 Kibana：

- `python3 quwoquan_service/scripts/tools/observability/es_cli.py daily-report --env <env> --output json`
- `python3 quwoquan_service/scripts/tools/observability/es_cli.py query --request-id <requestId> --output json`
- `python3 quwoquan_service/scripts/tools/observability/es_cli.py trace-samples --trace-id <traceId>`

按 CLI 产出的 `fingerprint` 聚类，优先处理 `nature=bug`、crash、panic、契约解析失败和
重复的 `errorCode + failurePoint + stackHash`。用 `traceId/requestId`、
`operationId + surfaceId/routeId/pageName`、`businessObject/functionModule`、
`entityType/entityId` 回链 owner。

只有能构造失败测试、smoke 命令、replay 请求或确定性本地脚本时才判为可复现；否则
生成脱敏 `report-only` 结论并停止，不从日志猜修复。

## 完成证据

逐 fingerprint 交付脱敏报告，至少包含 fingerprint、errorCode/nature、受影响环境和版本、
对象/模块、脱敏样本引用、复现命令与结果、owner，以及 `handoff-dev` 或 `report-only`
判定。不得包含原始 payload、token、完整 header、精确位置、SSID/IP、联系人或未脱敏
用户内容。

POST Review 先由主会话按 Review registry 解析并执行一次去重的命名 evidence，再调用
`review`（workflow=`incident-inspection`、segment=`POST`、
deliverable=`inspection-report`）。主审是 `observability`；命中运行诊断 profile 时至多
增加一个 `ops` 专审。Reviewer 只裁决已有证据，不运行 gate。required evidence 或
required Reviewer 未完成即返回 typed `GATE_BLOCK`。

## 失败与停止

- 始终只读，禁止改代码、配置或线上状态。
- 不把 `transient`、`requiresPermission`、`requiresUserAction` 在没有 app/cloud 缺陷证据
  时归类为代码 bug。
- 不使用退役关联键：`currentLogType`、`cloudRequestId`、`journeyId`、泛用
  `spanId/parentSpanId/correlationId`、`pythonJobId`。
- 凭证、样本或复现证据缺失时如实报告 typed blocker，不估算、不编造；用户取消或查询
  中断不得包装为完成。

## 条件性交接

仅在跨会话未完成、多人并行、外部阻断或证据需要后续复用时持久化交接。可复现代码
缺陷只交给 `dev`，附 fingerprint、脱敏样本、owner、复现命令及结果；不可复现项保留
`report-only` 和继续观察条件。普通已闭环巡检只向用户交付报告、证据和未决项，不建立
持久 HANDOFF 或第二状态台账。
