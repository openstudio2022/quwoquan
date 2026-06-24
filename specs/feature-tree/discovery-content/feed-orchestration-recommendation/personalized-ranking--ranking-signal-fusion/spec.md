# L4 特性：ranking-signal-fusion

## 功能说明

融合多路排序信号生成 feed 最终分。交集系统（`intersection-unified-experience`）的 fact/affinity 信号**必须经本 fusion 注入**，禁止另起 intersection-only ranker。

### 交集信号输入（与 §19.4 对齐）

| 信号 | 来源 | 通道 | 默认权重策略 |
|---|---|---|---|
| `intersectionFactStrength` | viewer×object fact reasons | fact | 高于 affinity |
| `intersectionFreshness` | freshAt/expiresAt | fact | 衰减 |
| `affinityIntersectionScore` | RecommendationAffinity / score API | affinity | 低于 fact，须 confidenceLabel |
| `qualityScore` / `recScore` | rm_discovery_feed 投影 | item quality | 只读投影结果，不同步打分 |
| `contentVertical` / `supplySource` | 数据工程 / UGC 投影 | context | 用于旅行、精品、供给分桶 |
| `intersectionCooldownPenalty` | rec:icool 命中 | 附着层 | 抑制重复 |

配置真相源：`recommendation/rec_model/policy.yaml`（与 feed_intersection_mixer 70/20/10 附着职责分离）。

## 约束

- 契约与字段策略必须与 metadata 保持一致。
- 交集 kind 注册表唯一真相源：`specs/product/intersection-definition-and-application.md` §5.4。
- 本轮禁止新增 intersection-only ranker，也不把 `/v1/score` 同步塞进 feed 读路径。
- `affinityIntersectionScore` 没有 `intersectionConfidenceLabel` 时不得参与候选级融合。

## 验收标准

- A1：feature_registry 含 intersection 特征且 fusion 文档引用同一字段名。
- A2：质量分、垂类、供给来源和交集候选特征进入 `ContentCandidate`，排序公式只消费 policy.yaml 权重。
- A3：fact 交集权重高于 affinity；affinity 缺 confidenceLabel 时不参与加分。
- A7：契约一致性校验通过。
- A8：无第二套 intersection 排序 service.yaml。
