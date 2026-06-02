# L2 特性：feedback-optimization-loop（反馈优化大循环）

## 功能说明

把"行为反馈 → 兴趣/人群画像 → 推荐策略自调建议 → 人审发布"串成一个**大循环**，
实现「内容飞轮」的算法侧闭环。能力边界覆盖：

1. **反馈采集与统一**（L3 `feedback-collection-unification`）
   - 端侧行为信号经 `content-service` HotPath 归一，投影到 `rm_recommend_feature`
     的 `userFeatures`（四维 affinities / ENER / 深度等）。
   - `InterestProfileAggregator` 基于四维 affinities 派生 `interestProfile`
     （topN 兴趣 + 生命周期分层 + 半衰期新鲜度衰减），并按
     `recommendation/rec_model/segments.yaml` 规则匹配人群 `segments`。
   - 派生结果经 `UserInterestRecomputed` 事件投影到 user 域
     `rm_user_profile_view.interestProfile/segments`（user 域单一真相源，供小艺主动）；
     `segments` 同步 `$set` 回 `rm_recommend_feature` 顶层供推荐引擎定向。

2. **优化评估与发布**（L3 `optimization-evaluation-and-release`）
   - 推荐评分策略全部元数据化于
     `contracts/metadata/recommendation/rec_model/policy.yaml`：12 维权重预设、
     二级系数、AB 实验、segment 定向、护栏。
   - `runtime/recpolicy.Store` 热加载该 YAML（`atomic.Pointer` + validate-before-swap
     + last-good 保留）；`codegen_rec_policy` 生成强类型 baseline 仅作 fail-safe。
   - 推荐引擎按解析后的 `ResolvedPolicy` 取权重/系数/实验分桶/segment 定向打分与重排，
     `PipelineMetrics` 落 `policyVersion / scoringPreset / segment / bucket` 作效果归因。
   - `scripts/recommendation/rec_policy_advisor.py` 对照 policy 护栏（`suggest_only`）
     评估 cohort KPI，**只产建议**并至多把候选推进到 product-ops 控制面 `:simulate`
     （停在 `simulated` 态）；**绝不** `:activate`，发布由人在 ops-portal 走双审。

## 约束

- **metadata-first / single-source**：评分权重、二级系数、实验、segment 定向、护栏的
  唯一真相源是 `policy.yaml`；人群规则唯一真相源是 `segments.yaml`；引擎/脚本禁止
  硬编码第二套权重或人群判定。改行为先改 metadata，再 `make codegen-rec-policy`。
- **画像单一真相源**：对外兴趣画像落在 user 域 `rm_user_profile_view`；
  `rm_recommend_feature.segments` 与事件投影均为同一 `MatchSegments` 计算的 CQRS
  投影，非第二真相源。
- **suggest-only 护栏**：`policy.yaml` 所有 `guardrails.action` 必须为 `suggest_only`；
  顾问脚本无任何 `:activate` 代码路径，护栏命中只产 `reject/hold` 建议，不自动回滚/切换。
- **热更不失稳**：坏 YAML 经 `Validate` 拒绝并保留 last-good，绝不"坏 YAML 置零打分"
  或导致引擎崩溃；启动前用 codegen baseline 兜底。
- **跨服务事件**：`UserInterestRecomputed` 走 `repository.DomainEvent` + Redis Pub/Sub，
  content 生产、user 消费；payload 字段以 `events.yaml` 为准。

## 验收标准（A1~A8 重点组）

- A1 功能闭环：行为反馈→画像/人群→策略解析→引擎打分→归因指标全链路可执行。
- A2 元数据驱动：权重/系数/实验/定向/护栏改 `policy.yaml` 即生效（热更），无需改代码。
- A3 容错：坏 policy 被拒并保留 last-good；缺实验/缺 baseline 走声明式 fallback。
- A4 人群定向：命中 segment 的用户按 `segmentTargeting` 解析出 preset 覆盖 / 权重增量。
- A5 顾问只产建议：护栏评估输出 `recommend_review/hold/reject`，至多调 `:simulate`，无 activate。
- A6 可观测归因：`PipelineMetrics` 与 `rec_requests_by_policy_total` 按
  `policyVersion × preset × segment` 切分。
- A7 契约一致：`policy.yaml` / `events.yaml` / `recommend_feature.yaml` /
  `user_profile_view.yaml` 通过 `make verify-metadata`。
- A8 自动化测试映射完整：见下方两个 L3 story 的 `tests.recorded`。
