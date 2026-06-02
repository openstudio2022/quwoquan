# L3 特性：baseline-comparison（基线对照 / champion-challenger）

## 功能说明

发布前必须用候选策略/预设/模型与"基线"对照，达标才进入人审：

- **基线定义**：评分预设基线为 `control`（`policy.yaml` `defaultPreset`）；模型基线为
  `champion`（`ExpModelVersion` 默认桶）；规则 vs 模型基线为 `rule`（`ExpModelVsRule` 默认桶）。
- **分桶对照**：`policy.yaml` AB 实验把流量按一致性哈希分到 `control/challenger` 桶；
  `PipelineMetrics` 落 `scoringPreset / segment / bucket / modelUsed`，
  `rec_requests_by_policy_total` 按 `policyVersion×preset×segment` 切分，使每个桶的
  曝光/互动可独立统计。
- **护栏相对基线**：`policy.yaml` `guardrails` 以相对基线的 `minRatio`（如互动率不得低于
  基线 95%）+ 绝对 `minSamples` 表达；`rec_policy_advisor` 对每个候选 cohort 逐指标比对，
  任一指标跌破即 `reject`，全部达标才 `recommend_review`。
- **发布闸**：达标候选至多推进到 product-ops `:simulate`（`simulated` 态），由人审在
  ops-portal 双签后才 `:activate`；顾问无 activate 路径。

## 约束

- 基线身份（control/champion/rule）唯一来自 `policy.yaml`，禁止脚本另立基线。
- 护栏比对必须相对基线（minRatio）而非绝对阈值拍脑袋；样本不足只能 hold。
- 任一指标 reject 即整体 reject（reject 支配 review），不得"挑好指标过关"。

## 验收标准

- A1：候选 cohort 可逐指标与基线对照得出 recommend_review/hold/reject。
- A2：reject 支配——多指标中任一跌破基线 minRatio 即整体 reject。
- A3：样本不足 → hold（缺 baseline 同样 hold，不误判）。
- A6：归因指标按 preset×segment×bucket 切分，基线与候选可分别统计。
- A8：对应自动化测试映射完整（见 acceptance.tests.recorded）。
