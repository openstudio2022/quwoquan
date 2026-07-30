# L2 Business Capability：反馈优化闭环 (`feedback-optimization-loop`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

反馈优化大循环：行为反馈 → 兴趣/人群画像派生 → 元数据驱动的推荐策略解析与自调建议 → 人审发布。算法侧闭环（content 派生 + user 投影 + recpolicy 热加载引擎 + 顾问 suggest-only）。

## 2. 范围与非目标

### In Scope

- 行为反馈归一到 rm_recommend_feature + 派生 interestProfile/segments（content-service）
- UserInterestRecomputed 事件投影到 user 域 rm_user_profile_view（单一真相源）
- policy.yaml 元数据化评分权重/二级系数/实验/segment 定向/护栏
- runtime/recpolicy Store 热加载（atomic + validate-before-swap + last-good）+ codegen baseline fail-safe
- 推荐引擎从 ResolvedPolicy 取权重/系数/分桶/定向；PipelineMetrics 归因 policyDigest/preset/segment
- rec_policy_advisor 只产建议 + 至多 :simulate（绝不 :activate）

### Out of Scope

- 策略激活/灰度/回滚的实际执行（由 product-ops 控制面 + ops-portal 人审双签完成）
- 模型训练与离线特征工程（属 recommendation-service / ML 管线）

## 3. Journey / Scenario 贡献

- [`JNY-002 / SCN-005`](../../spec.md#scn-005)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：反馈优化大循环：行为反馈 → 兴趣/人群画像派生 → 元数据驱动的推荐策略解析与自调建议 → 人审发布。算法侧闭环（content 派生 + user 投影 + recpolicy 热加载引擎 + 顾问 suggest-only）。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`feedback-collection-unification`](./feedback-collection-unification/spec.md)：从行为反馈派生画像与人群，并向推荐域和用户域双路投影。
- [`optimization-evaluation-and-release`](./optimization-evaluation-and-release/spec.md)：策略只从 metadata 加载，坏配置拒绝生效并保留 last-good。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 反馈优化闭环能力组合结果

- 行为反馈→派生 interestProfile/segments→事件投影 user 域→segments 回写宽表 全链路可验证。
- policy.yaml 改权重/系数/实验/定向即热生效（Store.Apply 校验通过即原子切换），坏 YAML 保留 last-good。
- 引擎按 ResolvedPolicy 打分/重排，命中 segment 的用户按 segmentTargeting 取 preset 覆盖/权重增量。
- PipelineMetrics 与 rec_requests_by_policy_total 按 policyDigest×preset×segment 归因。
- rec_policy_advisor 评估护栏后只产 recommend_review/hold/reject 建议，至多调 :simulate，无 activate 路径。
- 大循环实证脚本跨 content/user 两库断言行为→派生→双路 CQRS 投影→引擎可定向闭合，且宽表与画像两路 segments 一致（单一 MatchSegments 源）。
- 飞轮评估 dashboard（l2_content_flywheel）按派生/投影/引擎归因/互动/主动个性化各环节可视化，配套告警覆盖派生失败率、投影失败与新鲜度滞后。

<a id="req-002"></a>
### REQ-002 suggest-only 护栏：`policy.yaml` 所有 `guardrails.action` 必须为 `suggest_only`

- **suggest-only 护栏**：`policy.yaml` 所有 `guardrails.action` 必须为 `suggest_only`。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 反馈优化大循环能力 SIT（端云协同 + 元数据驱动 + 顾问 suggest-only）

- GIVEN 执行“反馈优化大循环能力 （端云协同 + 元数据驱动 + 顾问 suggest only）”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“反馈优化大循环能力 （端云协同 + 元数据驱动 + 顾问 suggest only）”对应动作。
- THEN 行为反馈→派生 interestProfile/segments→事件投影 user 域→segments 回写宽表 全链路可验证。
- THEN policy.yaml 改权重/系数/实验/定向即热生效（Store.Apply 校验通过即原子切换），坏 YAML 保留 last-good。
- THEN 引擎按 ResolvedPolicy 打分/重排，命中 segment 的用户按 segmentTargeting 取 preset 覆盖/权重增量。
- THEN PipelineMetrics 与 rec_requests_by_policy_total 按 policyDigest×preset×segment 归因。
- THEN rec_policy_advisor 评估护栏后只产 recommend_review/hold/reject 建议，至多调 :simulate，无 activate 路径。
- THEN 大循环实证脚本跨 content/user 两库断言行为→派生→双路 CQRS 投影→引擎可定向闭合，且宽表与画像两路 segments 一致（单一 MatchSegments 源）。
- THEN 飞轮评估 dashboard（l2_content_flywheel）按派生/投影/引擎归因/互动/主动个性化各环节可视化，配套告警覆盖派生失败率、投影失败与新鲜度滞后。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 反馈优化大循环能力 SIT（端云协同 + 元数据驱动 + 顾问 suggest-only）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：行为反馈→派生 interestProfile/segments→事件投影 user 域→segments 回写宽表 全链路可验证。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
