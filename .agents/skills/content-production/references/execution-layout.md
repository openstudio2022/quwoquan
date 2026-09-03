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

`task init` create-once 写根 manifest 与 `0.plan` 两份输入。`stage-open` create-once 冻结显式 input refs；`stage-close` create-once 写宿主提交且经内核重验的结果。工作包内不存在 execution-state、claim、queue、checkpoint、runner 或 recovery 根。

对象根与阶段必需产物以 schema/当前 stage contract 为准。宿主不得创建 taskId、batchId、workerId、laneId、campaignId 等平行运行身份。

## canonical、release 与环境

- approved 对象逐个经单对象事务原子写入 canonical publish；
- immutable release 只消费宿主 AI 显式 cohort；
- 环境 import/readback/health/EAF 写 append-only environment run facts；
- canonical 不包含 raw source、草稿、prompt、日志、receipt 或运行状态；
- 禁止 dual-read、旧路径 fallback、shim 与 sequence-017 兼容。
