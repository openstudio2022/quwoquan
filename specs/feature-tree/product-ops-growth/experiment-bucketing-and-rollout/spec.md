# L2 特性：experiment-bucketing-and-rollout

## 功能说明

统一的实验分桶与灰度发布地基：以 `experimentBucket` 作为公共维度贯穿端云埋点、推荐策略、ops 看板，
支持按桶切分指标、评估 uplift、回滚影响。分桶在端侧上下文与云侧策略协同决定，App 只有一个 `prod` 包
（不存在 `app-prod-gray`），灰度由应用市场分发 + 端侧上下文 + 云侧 prod-gray 策略控制。

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
- 实验指标必须复用 `analytics-metric-dictionary` 主口径，不得绕过字典直接进 dashboard。
- 生产包纯净：`kReleaseMode` 不暴露 mock/remote 切换或等价灰度入口；灰度由分发 + 端侧上下文 + 云侧策略控制。

## 验收标准

- A1：`experimentBucket` 作为公共维度贯穿端云埋点，可按桶切分核心指标。
- A2：交集策略变体可按桶切分并评估对 `intersection_conversion_rate` 的 uplift（按 dimension/action 下钻）。
- A3：交集行动端云携带 `experimentBucket`，服务端按桶可分；变体可独立回滚，回滚影响可度量。
