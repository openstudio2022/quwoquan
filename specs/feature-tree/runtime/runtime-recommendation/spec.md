# L2 Business Capability：运行时推荐 (`runtime-recommendation`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

提供推荐 HotPath、SessionCache、Engine、Scorer 与 Rerank 的统一运行时，使候选排序、降级和观测使用同一会话与策略边界。

## 2. 范围与非目标

### In Scope

- Redis HotPath session 状态、negative/exposed/tag weights/realtime interest。
- 7 阶段 Engine 管线、多源召回、预排、过滤、特征组装、打分、重排。
- RuleScorer、RemoteModelScorer、CascadeScorer fallback。
- MMR/UCB1 探索、多样性、冷启动保底、SessionCache 与 BufferedHotPath。

### Out of Scope

- 首页 feed IA、频道布局、页面 route/surface；归 discovery-content/feed-orchestration-recommendation。
- 深度排序模型平台轨与双塔 ANN 在线服务。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)：**SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime recommendation 引擎能力 SIT

- HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- Engine 7 阶段管线在召回源超时、模型 scorer 失败、候选重复、冷启动等场景下仍返回稳定结果或明确空态。
- RuleScorer 消费用户特征、交集信号、搜索意图、负反馈惩罚、UCB1 探索和 MMR 多样性。
- `SessionCache`、`BufferedHotPath` 与 Redis key hash-tag 必须在 pipeline 和 parallel 路径保持同一会话状态语义。

<a id="req-002"></a>
### REQ-002 CascadeScorer 保证 ML 不可用时降级到 RuleScorer

- CascadeScorer 保证 ML 不可用时降级到 RuleScorer。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime recommendation 引擎能力 SIT

- GIVEN 执行“runtime recommendation 引擎能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime recommendation 引擎能力”对应动作。
- THEN HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- THEN Engine 7 阶段管线在召回源超时、模型 scorer 失败、候选重复、冷启动等场景下仍返回稳定结果或明确空态。
- THEN RuleScorer 消费用户特征、交集信号、搜索意图、负反馈惩罚、UCB1 探索和 MMR 多样性。
- THEN pipeline 与 parallel 路径读取相同会话状态，Redis key 落在预期 hash slot，重放不重复更新。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime recommendation 引擎能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
