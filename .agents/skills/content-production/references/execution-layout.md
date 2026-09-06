# execution 布局与交接事实

## 可复用工程输入

可复用输入仍只来自受治理的 `control_plane`、`verticals`、`reference`、`prompts`、`templates` 与 `schema`。execution-specific 区域、目标、数量与 candidate bindings 只由 `task init` 冻结，禁止回写可复用配置。

## 单 execution 工作包

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/**/<1.download..5.review>/
  posts/<carrier>/**/<1.download..5.review>/
  _shared/
    stage-open/<sequence>-<stage>.json
    receipts/<sequence>-<stage>.json
  evidence/
    publish_refs/
```

`task init` create-once 写根 manifest 与 `0.plan` 两份输入。`stage-open` create-once 冻结 AI 点名的 exact input refs；`stage-close` create-once 写 AI 提交且经内核重验的结果。producer stage 闭集到 sequence 009 的 `release` 为止；producer 枚举与 OPEN/CLOSE schema 已拒绝 sequence 010 `ship`，既有 ship CLI 仅作为下游独立入口。

工作包内不存在 execution-state、claim、queue、checkpoint、runner、recovery 或环境阶段根。对象根与阶段必需产物以 schema/当前 stage contract 为准。宿主不得创建 taskId、batchId、workerId、laneId、campaignId 等平行运行身份。

## canonical、release 与下游环境

- approved 对象逐个经单对象事务原子写入 canonical publish；
- immutable release 只消费宿主 AI 显式 cohort；
- producer handoff 只暴露 immutable release/cohort/content-pool refs、digests、milestone、carrier counts 与 producer baseline revision；
- producer handoff 不含 import/readback/health/UAT/EAF 或 sampling authority；任何下游 consumer facts 都不写回 execution；
- canonical 不包含 raw source、草稿、prompt、日志、receipt 或运行状态；
- 禁止 dual-read、旧路径 fallback、shim 与 sequence-017 兼容。
