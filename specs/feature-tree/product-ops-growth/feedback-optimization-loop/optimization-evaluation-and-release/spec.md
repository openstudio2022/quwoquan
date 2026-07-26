# L3 Story：optimization-evaluation-and-release（策略评估与发布） (`optimization-evaluation-and-release`)

> 所属能力：[`feedback-optimization-loop`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，
我希望基于真实归因指标评估推荐策略建议，并只将经审批的版本灰度发布，
从而获得可度量、可回滚且不会自动越权生效的优化结果。

## 2. 范围与非目标

### In Scope

- policy.yaml 权重/系数/实验/segment 定向/护栏（元数据真相源）
- recpolicy.Store 热加载（atomic + validate-before-swap + last-good）+ codegen baseline fail-safe
- 引擎从 ResolvedPolicy 取权重/系数/分桶/重排阈值；PipelineMetrics 归因
- rec_policy_advisor 护栏评估 + suggest-only + 至多 :simulate
- policy.yaml 基线身份（defaultPreset=control / champion / rule）+ AB 分桶
- PipelineMetrics 与 rec_requests_by_policy_total 按 preset×segment×bucket 归因
- rec_policy_advisor 逐指标相对基线 minRatio 比对 + reject 支配 + 样本不足 hold

### Out of Scope

- 策略激活(activate) / 灰度 / 回滚的执行（product-ops 控制面 + ops-portal 人审双签）
- 候选激活/灰度（product-ops 控制面 + ops-portal 人审双签）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 元数据驱动策略热加载与引擎解析

- 通过校验的 metadata 策略可原子生效；坏 YAML 必须被拒绝并继续使用 last-good。

<a id="req-002"></a>
### REQ-002 顾问只产建议且不得激活策略

- 顾问只能产出结构化建议，最多将候选推进到 `:simulate`；不得调用 `:activate` 或直接写入生效状态。

<a id="req-003"></a>
### REQ-003 评分相关一切数字（权重/系数/实验比例/定向/阈值）唯一来自 policy.yaml；引擎与脚本禁止硬编码

- 评分相关一切数字（权重/系数/实验比例/定向/阈值）唯一来自 `policy.yaml`；引擎与脚本禁止硬编码。
- 热更必须 validate-before-swap；坏 YAML 拒绝并保留 last-good，禁止"坏 YAML 置零打分"。

<a id="req-004"></a>
### REQ-004 候选相对基线逐指标对照得出发布建议

- 候选必须逐指标与 `baselinePreset` 对照；任一指标不满足护栏时整体拒绝，样本不足时保持 `hold`。

<a id="req-005"></a>
### REQ-005 护栏以相对基线和最小样本共同裁决

- `policy.yaml` 的每个 guardrail 必须声明 `baselinePreset`、`minRatio`、`minSamples`、`window` 与 `suggest_only` 动作。
- 基线身份（control/champion/rule）唯一来自 `policy.yaml`，禁止脚本另立基线。
- 护栏比对必须相对基线（minRatio）而非绝对阈值拍脑袋；样本不足只能 hold。
- 任一指标 reject 即整体 reject（reject 支配 review），不得"挑好指标过关"。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`
- canonical：`runtime/recpolicy/rec_policy_baseline.gen.go`
- canonical：`contracts/metadata/_control_plane/product/workflow.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 元数据驱动策略热加载与引擎解析

- GIVEN policy.yaml 定义了 control/engagement_heavy 等预设、实验与 segment 定向。
- GIVEN recpolicy.Store 已 seed codegen baseline 并热加载 policy.yaml。
- WHEN 编辑 policy.yaml 调整权重/系数（合法）后被 Store.Apply 应用。
- WHEN 写入一份结构非法的 policy.yaml。
- THEN 合法变更原子切换、EffectiveHash 改变、引擎按新权重打分。
- THEN 非法变更被 Validate 拒绝并保留 last-good，引擎打分不受影响。

<a id="gwt-002"></a>
### GWT-002 顾问只产建议且至多 :simulate（绝不 activate）

- GIVEN policy.yaml 护栏 action 全部为 suggest_only。
- GIVEN 给定一组 cohort KPI（preset×segment×bucket）。
- WHEN 运行 rec_policy_advisor 评估护栏。
- THEN 达标候选标 recommend_review，回归候选标 reject，样本不足标 hold；全部 action=suggest_only。
- THEN 脚本至多调用 :simulate；模块不存在任何 activate 能力（call_activate/activate_url 不存在）。

<a id="gwt-003"></a>
### GWT-003 候选相对基线逐指标对照得出发布建议

- GIVEN policy.yaml 定义 control 基线与候选 preset，护栏含相对 minRatio 与绝对 minSamples。
- GIVEN 给定候选 cohort 多项 KPI（部分达标、部分跌破基线）。
- WHEN rec_policy_advisor 逐指标与基线对照。
- THEN 全部指标达标且样本充足 → recommend_review。
- THEN 任一指标跌破基线 minRatio → 整体 reject（reject 支配 review）。
- THEN 样本不足或缺 baseline → hold。

## 6. 依赖

- 前置要求：[`feedback-optimization-loop`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 元数据驱动策略热加载与引擎解析

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：改 metadata 即生效且坏 YAML 不失稳的闭环可由单测证明。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 顾问只产建议且至多 :simulate（绝不 activate）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：顾问"只产建议 + 至多 :simulate + 无 activate"可由单测证明。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 候选相对基线逐指标对照得出发布建议

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：相对基线对照 + reject 支配 + 样本门槛的发布判定可由单测证明。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
