# L3 Story：feedback-collection-unification（反馈采集与统一） (`feedback-collection-unification`)

> 所属能力：[`feedback-optimization-loop`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，我希望行为反馈归一为画像与人群信号：content 派生 interestProfile/segments（MatchSegments 单一计算源）→ UserInterestRecomputed 事件投影 user 域 rm_user_profile_view → segments ，从而获得可度量、可回滚的运营结果。

## 2. 范围与非目标

### In Scope

- HotPath 行为信号归一到 rm_recommend_feature.userFeatures + 半衰期衰减作业
- InterestProfileAggregator 派生 interestProfile + MatchSegments 匹配人群
- 两路 CQRS 投影：UserInterestRecomputed→user 域；segments $set 回 rm_recommend_feature 顶层
- InterestDecayJob 四维 affinities 半衰期衰减（解 $inc 单调累积）
- verify_behavior_action_consistency 行为-动作枚举端云一致门禁
- rec_policy_advisor 样本不足 cohort 一律 hold

### Out of Scope

- 端侧埋点采集与上报（属 app 客户端 + content 上报契约）
- 策略评估/发布（见 optimization-evaluation-and-release）
- 反爬/风控/账号封禁等安全治理（属安全域）
- 端侧采集与上报本身（属 app 客户端）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 行为反馈派生画像/人群并双路投影

- 行为反馈必须派生为兴趣画像与规则人群，并分别投影到推荐域与用户域。

<a id="req-002"></a>
### REQ-002 人群规则唯一真相源 `segments.yaml`

- 人群规则唯一真相源 `segments.yaml`；判定只走 `MatchSegments`，禁止散落 if-else 第二套人群逻辑。

<a id="req-003"></a>
### REQ-003 去噪与样本门槛保障反馈质量

- 旧兴趣按 metadata 半衰期衰减；样本不足的 cohort 必须保持 `hold`，不得产生发布建议。

<a id="req-004"></a>
### REQ-004 衰减半衰期、样本门槛等参数均来自 metadata（`segments.yaml` / `policy.yaml`），禁止硬编码

- 衰减半衰期、样本门槛等参数均来自 metadata（`segments.yaml` / `policy.yaml`），禁止硬编码。
- 样本不足只能 `hold`，禁止"零样本默认达标"或"零样本默认 reject"。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/recommend_feature.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/events.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/recommend_feature.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/projections/user_profile_view.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 行为反馈派生画像/人群并双路投影

- GIVEN 某用户在 rm_recommend_feature.userFeatures 已累计四维 affinities（含旅行类高亲和）。
- GIVEN segments.yaml 定义了 travel_enthusiast 等规则人群。
- WHEN InterestProfileAggregator.Recompute 运行。
- THEN 派生出 topN interestProfile + 生命周期分层，MatchSegments 命中对应 segments。
- THEN 发布 UserInterestRecomputed 事件且投影到 user 域 rm_user_profile_view.interestProfile/segments。
- THEN segments 同步 $set 回 rm_recommend_feature 顶层供引擎定向。

<a id="gwt-002"></a>
### GWT-002 去噪与样本门槛保障反馈质量

- GIVEN 某用户既往累计旧兴趣 affinities，近期无新行为。
- GIVEN 某 cohort 样本量低于护栏 minSamples。
- WHEN InterestDecayJob 运行；rec_policy_advisor 评估该 cohort。
- THEN 旧兴趣 affinities 按半衰期单调下降，画像反映近期偏好。
- THEN 样本不足 cohort 一律标 hold，不产 recommend_review/reject。

## 6. 依赖

- 前置要求：[`feedback-optimization-loop`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 行为反馈派生画像/人群并双路投影

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：派生→双路投影闭环可由 content/user 两侧单测证明。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 去噪与样本门槛保障反馈质量

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：衰减去噪 + 样本不足 hold 的质量控制可由单测证明。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
