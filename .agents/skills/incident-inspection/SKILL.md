---
name: incident-inspection
description: Read-only inspection of production exception telemetry - query Elasticsearch, group fingerprints, produce redacted daily reports, triage priority and owner, and judge reproduction eligibility before any fix. Make sure to use this skill whenever the user mentions ES, 异常监控, 线上错误, 线上异常, 巡检, 日报, exception triage, fingerprint, traceId, or requestId, even without an explicit command.
metadata:
  kind: workflow
---

# incident-inspection

## 触发与输入

用于线上异常、ES 巡检/日报、fingerprint 分组、traceId/requestId 调查与复现资格判断。输入是环境、时间窗或脱敏查询 identity；角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.incident-inspection`，可见输出由 canonical projector 生成。

本轮若将产生或更新 registry 声明的送审交付件 `inspection-report`，每份 report 的全部 fingerprint 必须先由 current canonical correlation/ContractGraph owner facts 解析到同一个 `specRef` 去锚点后的 repository-relative canonical Feature `spec.md` exact target；跨 owner 结果必须拆成多份 report。缺 owner、同一 report 多 target 或无法唯一解析时返回 typed `GATE_BLOCK`，不得送审。随后运行 `make feature-context TARGET=<exact-path>`，保存 stdout 指向的 content-addressed immutable owner manifest exact ref，PRE 后不得重写或替换该 ref。

## 执行

只使用稳定 observability CLI 查询与聚类，按 canonical correlation facts 回链 owner。遥测查询、脱敏与 fingerprint 聚类只加载 [telemetry-inspector.md](references/roles/telemetry-inspector.md)，影响定级与 owner 回链只加载 [incident-triager.md](references/roles/incident-triager.md)，构造测试、smoke、replay 或本地脚本及判定复现资格只加载 [reproduction-analyst.md](references/roles/reproduction-analyst.md)；不预载无关角色正文。只有存在确定性复现证据时才判可复现，否则输出 report-only。

本工作流保持只读，不修改源码、配置或线上状态。仅返回临时查询结果、且用户未要求保存或送审 `inspection-report` 时，可不生成 owner manifest；此类请求必须以明确的 `read-only/no-review-deliverable`、`report-only/no-review-deliverable` 或 typed blocker 终止，不得调用 POST Review。需要源码/spec mutation 时，以可复现证据和已定位路径交接 explore/prd/design/dev；本 Skill 不自行修复。

## 完成证据

逐 fingerprint 交付脱敏报告、影响环境/版本、对象/模块、样本引用、复现命令与结果、owner，以及 handoff-dev 或 report-only 判定；不包含 secret/PII/raw payload。稳定查询入口是 `python3 quwoquan_service/scripts/tools/observability/es_cli.py triage --domain <product|platform> ... --output <json|markdown>`；若 canonical Product/Platform Ops API、样本级 identity 或确定性复现证据不可用，则只允许无送审的 `report-only/no-review-deliverable` 终态或 typed blocker，不虚构 trace/request 查询命令。

产生 `inspection-report` 时，POST 默认零 Reviewer，只报告命名 evidence 结果并保留 PRE 的 owner manifest exact ref；仅在用户显式 `/review` 或 report 进入 handoff 准出时，才把同一 ref 原样作为 `--context-manifest` 传给 Review（workflow=`incident-inspection`、segment=`POST`、deliverable=`inspection-report`、scope=`<exact-path>`）。manifest ref 缺失、与 PRE 不同或 stale 时不得声称已送审。

## 失败与停止

凭据、样本、唯一 owner/exact target、复现证据或送审 owner manifest 缺失时如实返回 typed blocker；不把 transient/permission/user action 在无缺陷证据时归为代码 bug，不把无送审 report-only 包装成已评审 `inspection-report`。

## 条件性交接

源码/spec mutation 只交 Feature workflow；跨会话、外部阻断或用户显式要求满足 canonical 触发时生成 handoff。送审交付的 handoff 必须携带 PRE 保存并在 POST 原样复用的 owner manifest exact ref；纯只读无送审交付不生成替代 manifest。
