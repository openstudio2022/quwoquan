# L3 Story：交集算法闭环（Feature / Ranking / Explain / Event）

## 节点定位

- `L1_domain_service`: `object-homepage-network`
- `L2_business_capability`: `intersection-unified-experience`
- `L3_story`: `intersection-algorithm-closure`

## 功能说明

把 §19 算法闭环落成可实施规格：Event 回流 → Feature 宽表 → ranking-signal-fusion 注入 → Explain primaryText 产出。与 `feed-orchestration-recommendation` 共享排序真相源，禁止第二套 ranker。

真相源：[intersection-definition-and-application.md](../../../../product/intersection-definition-and-application.md) §19。

## 范围

### Event

- content `behaviors.yaml`：impression/click 补 `intersectionSourceRef`；新增 `intersection_expand`。
- 转化 follow/join 补 sourceRef 归因。

### Feature

- `recommend_feature.yaml` → `socialFeatures.intersection.*`
- `services/rec-model-service/scripts/feature_registry.yaml` 同步字段
- rec-model-service `transformer.py` 消费 intersection 特征（实现会话）

### Ranking

- `personalized-ranking--ranking-signal-fusion`：登记 intersection fact/affinity 信号权重
- `feed_intersection_mixer` 70/20/10 附着层与排序层职责分离

### Explain

- `IntersectionService` Explain 管线产出 primaryText（禁止 hydrate 回退 displayText）
- kind → 主谓宾模板注册表（与 §5.4 / §17.1 对齐）

## Out of Scope

- Graph 多跳传播影响（P2）
- 独立 Transformer 精排模型训练（可迭代，但 feature_registry 须先就位）

## 验收标准概要

- A1：feature_registry 含 ≥4 个 intersection 特征字段
- A2：ranking-signal-fusion spec 引用 intersection 信号，无第二 ranker 文档
- A3：contract 测试断言 primaryText 来自 Explain 管线，非 displayText 回退
- A4：行为事件 payload 含 intersectionSourceRef
