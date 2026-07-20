# L2 特性：experiment-bucketing-and-rollout

## 功能说明

统一的实验分桶与灰度发布地基：以 `experimentBucket` 作为公共维度贯穿服务端策略、实际曝光/查询事实
与指标聚合，支持按桶切分指标、评估 uplift、回滚影响。分桶由服务端
`runtime/experiments.AssignBucket` 权威决定，客户端上报的 bucket 不作为真相源。App 只有一个 `prod` 包
（不存在 `app-prod-gray`），灰度由应用市场分发 + 端侧可信上下文 + 云侧 prod rollout 策略控制。

当前商用基线明确冻结为单轨：

- 推荐由 `runtime/recpolicy` 消费 metadata/codegen policy，并复用
  `runtime/experiments.AssignBucket`；搜索由同一 runtime resolver 分桶。
- 审计与效果统计只消费实际下发的推荐曝光事实、行为事实和搜索查询事实中的
  `experimentBucket`，不得消费未进入线上热路径的模拟 assignment。
- Product Ops `Experiment` / `ExperimentAssignmentFact` 在 durable runtime binding、
  policyVersion 原子发布、实际流量回写与 gamma 对账完成前保持 commercial blocked，
  Portal 不展示实验目录、rollout 或 assignment 统计。

### 交集策略实验地基（S6 增长商业化）

「交集」是全 App 北极星。交集策略（理由排序、解释文案、行动召唤）可作为实验变量，按 `experimentBucket`
切分并评估对交集转化北极星的影响：

- 实验单元：交集策略变体（如不同 `intersectionDimension` 优先级、不同行动召唤顺序 follow/join_circle/add_contact）。
- 评估指标：`intersection_conversion_rate`（北极星，见 `analytics-metric-dictionary`），按 `intersectionDimension` /
  `action` 下钻评估 uplift。
- 归因链：交集行动（follow/join_circle/add_contact）端云携带 `experimentBucket`（`RemoteBehaviorRepository`
  上报时注入），服务端 `BehaviorService` 与日指标按桶可分。
- 回滚：交集策略变体可独立回滚，回滚影响以北极星指标桶间差异度量。

## 约束

- 分桶口径唯一：`experimentBucket` 维度定义复用 `event-schema-governance`，不得各端各自维护第二套桶映射。
- 分桶算法唯一：推荐与搜索必须复用 `runtime/experiments`；禁止业务服务调用未绑定热路径的
  Product Ops assignment API 再做第二次分桶。
- 控制面 fail-closed：未接入实际线上流量的实验控制面必须 default-deny 且无 Portal 入口，不得把
  PostgreSQL assignment 统计呈现为线上实验结果。
- 实验指标必须复用 `analytics-metric-dictionary` 主口径，不得绕过字典直接进 dashboard。
- 生产包纯净：`kReleaseMode` 不暴露 mock/remote 切换或等价灰度入口；灰度由分发 + 端侧上下文 + 云侧策略控制。

## 验收标准

- A1：`experimentBucket` 作为公共维度贯穿端云埋点，可按桶切分核心指标。
- A2：交集策略变体可按桶切分并评估对 `intersection_conversion_rate` 的 uplift（按 dimension/action 下钻）。
- A3：交集行动端云携带 `experimentBucket`，服务端按桶可分；变体可独立回滚，回滚影响可度量。
- A4：推荐/搜索复用同一 runtime hash resolver，真实曝光/查询事实携带服务端权威 bucket。
- A5：静态门禁证明未绑定 runtime 的 Product Ops experiment/assignment 操作保持 blocked、
  推荐/搜索热路径不引用该轨道、Portal 不暴露实验控制面。
