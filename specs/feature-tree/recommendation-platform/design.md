# 设计：训练工程与模型服务分离

本设计说明为何在推荐平台下将「训练集部署工程」与「模型服务」拆成两个 L3、两种部署物，以及特性树与契约的划分方式。迁移已执行完毕，当前结构以本设计为准。

**设计原则（遵循 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`）**：对主题做业界最佳实践与标杆对比，给出多备选方案并选最优或可演进到最优；若当前采用轻量方案，则在 design 与 tasks 中明确未来演进与存量带规划任务。本设计：对标业界训练/推理分离与双塔等深度模型实践，备选见 §2，选定「训练 L3 + 推理 L3」分离；模型侧当前为 LightGBM/规则可回退的轻量方案，演进路径与规划任务见 [tasks.md](tasks.md) 的「规划任务」小节。

---

## 1. 实际部署形态

### 1.1 两种部署物

| 部署物 | 形态 | 调度/运行方式 | 对接方 |
|--------|------|----------------|--------|
| **训练镜像** | 批处理/任务 | PAI-DLC、火山 ML 工作流、cron 或事件驱动 | 多训练场景（content_feed / circle_discovery / friend_suggestion）；产出写入 ModelRegistry + OSS/TOS |
| **推理服务** | 常驻在线服务 | K8s/PAI-EAS/自建 7×24 运行 | Go 业务服务（content-service 等）通过 HTTP 调用 POST /v1/score |

- **训练侧**：SampleJoiner → rec_training_samples，DatasetManager → rec_datasets，FeatureTransformer + 训练脚本 → 模型文件 + 元信息，ModelRegistry → rec_model_registry + OSS/TOS。运行方式为**任务/作业**（定时或按需），非常驻 HTTP 服务。
- **推理侧**：FastAPI 应用，POST /v1/score、GET /health，按 scenario 加载 production 模型并返回 scores，需满足 Go 侧延迟预算（如 30–50ms）。

因此存在**两个可独立部署、独立扩缩的单元**：
1. **训练工程/训练集部署工程**：对接多 scenario、多数据集，产出写入 ModelRegistry，供下游加载。
2. **模型服务**：装载多 scenario 模型，对接 Go 应用服务，提供统一打分接口。

---

## 2. 业界对标与备选方案对比

**业界实践**：主流推荐/ML 平台（如大厂信息流、广告排序）普遍将「训练/离线」与「推理/在线」分离部署：训练为批/任务形态，推理为常驻服务；契约上训练产出写入模型注册与存储，推理侧按需加载。双塔、深度排序等重型模型也沿用同一分离架构，仅模型形态与特征管线升级。

**备选方案**：

| 方案 | 描述 | 优点 | 缺点 | 结论 |
|------|------|------|------|------|
| A. 单一体 rec-model-engineering-service（训练+推理同 L3） | 一个 L3 下两镜像（训练 job + 推理 service） | 叙事简单、共享代码 | 部署拓扑/SLA/运维边界混在一起，扩缩与故障域不清晰 | 不采用 |
| B. 训练 L3 + 推理 L3 分离（当前） | rec-model-training 与 rec-model-service 两个 L3，两服务 | 与部署形态一致、职责与 SLA 清晰、可独立扩缩与演进 | 需维护两处契约对齐（feature_registry、ModelRegistry） | **采用** |
| C. 训练/推理进一步拆多服务（如按 scenario 拆推理） | 每个 scenario 独立推理服务 | 极致隔离 | 运维与契约复杂度高，当前场景数量不必要 | 留作未来可选演进 |

**选定 B**：在满足「训练=任务、推理=常驻」的业界共识前提下，采用两 L3 分离，既具备竞争力又便于向双塔/深度模型演进（仅升级训练管线与模型格式，推理契约保持不变）；规划任务见 tasks.md。

---

## 3. 适用场景与约束

- **适用场景**：推荐场景（content_feed、circle_discovery、friend_suggestion 等）下，训练为批/任务、推理为常驻 HTTP 服务；团队规模可维护两服务、契约与 feature_registry 可对齐；当前模型为 LightGBM/规则，推理延迟预算在 30–50ms 量级。
- **约束与局限性**：训练侧当前无对外 HTTP API（仅作业/脚本触发），提交训练任务、按 scenario 拆推理服务等不在当前范围；多租户/多 region 部署、训练资源弹性调度策略需在部署层另行约定。不适用于非推荐域（如风控、搜索排序）的独立模型服务形态。
- **已知限制**：两 L3 共享 feature_registry 与 ModelRegistry 契约，变更时需双侧协同；推理侧强依赖 Registry/OSS 可用性。

---

## 4. 未来演进

- **目标态**：支持双塔等深度排序模型、TikTok/Facebook 式信息流重度深度学习（序列/多目标/实时特征），训练与推理仍为两 L3，契约保持 POST /v1/score 与 CandidateInput/CandidateScore 稳定。
- **当前差距**：模型形态为 LightGBM/规则；深度模型的特征管线、训练样本格式、模型注册格式需扩展；未提供「提交训练任务」等训练侧 API。
- **前置/触发条件**：业务需要更高排序效果、特征与样本管线就绪、训练/推理资源与延迟预算允许 heavier 模型时，在 tasks 的「未来演进任务」中逐项落地；对应 design 与 tasks 在对应 L4/L5 节点细化。
- **与 tasks 对应**：搁置任务见 [tasks.md#搁置任务带规划](tasks.md)；未来演进任务见 [tasks.md#未来演进任务](tasks.md)。

---

## 5. 分离理由与取舍（细化）

### 5.1 支持分离的理由

| 维度 | 说明 |
|------|------|
| **部署拓扑** | 训练 = 批/任务（短生命周期或按调度）；模型服务 = 长驻进程、高可用与延迟 SLA。扩缩与故障域不同。 |
| **职责边界** | 训练工程：样本、数据集、特征、训练、注册；模型服务：仅读 Registry/OSS，暴露 /v1/score。 |
| **SLA 与归属** | 训练关注吞吐、数据正确性、评估通过再打 production；模型服务关注延迟、可用性，与 content-service 等同属在线链路。 |
| **契约与元数据** | 模型服务对应 rec_model_service（POST /v1/score）；训练可先无对外 HTTP API（仅作业），或后续单独「提交训练任务」API。 |
| **服务清单** | 拆成 rec-model-training + rec-model-service，与架构图一致，运维与排障边界清晰。 |

### 5.2 保持共享的部分

- **共享**：同一 feature_registry、同一 ModelPredictRequest/Response 契约；训练与推理共用特征注册表与 schema。
- **实现**：可同代码库、两镜像；特性树中为两个 L3，部署文档中明确「训练 job」与「推理 service」两种部署方式。

---

## 6. 特性树与服务规划

### 6.1 L1 下 L3 结构

```
recommendation-platform (L1)
├── rec-model-training (L3)   # 训练集部署工程服务
│   ├── training-pipeline (L4)     # 样本、数据集、特征、训练、注册
│   │   └── sample-feature-train-registry (L5)
│   └── training-deployment (L4)   # 训练镜像、PAI/火山任务、调度
│       └── docker-and-cloud (L5)
│
└── rec-model-service (L3)    # 模型服务
    ├── inference-api (L4)         # POST /v1/score、scenario 路由、模型加载
    │   └── scenario-router-and-models (L5)
    ├── go-integration (L4)        # HTTP 契约、CascadeScorer 兜底
    │   └── http-contract-and-client (L5)
    └── inference-deployment (L4)  # 推理镜像、PAI-EAS/K8s、与 Go 联调
        └── docker-and-cloud (L5)
```

- **rec-model-training**：仅含训练管线与训练部署相关 L4/L5；不含 inference-api、go-integration。
- **rec-model-service**：仅含推理 API、Go 集成、推理部署相关 L4/L5；不含训练脚本与训练镜像的交付责任。
- **共享约束**：feature_registry、ModelRegistry 与 rec_model_registry/OSS 由平台层或两节点共同引用；训练产出与推理加载通过 Registry + OSS 解耦。

### 6.2 服务清单与契约

| 服务名 | 职责摘要 | 部署形态 | 对外契约（当前） |
|--------|----------|----------|------------------|
| **rec-model-training** | 多场景训练：样本→数据集→训练→注册 | 任务/作业 + 训练镜像 | 可选：无对外 API，或后续 POST /v1/jobs（提交训练任务） |
| **rec-model-service** | 多场景推理：装载模型、POST /v1/score | 常驻推理服务 | 已有：POST /v1/score、GET /health（contracts/metadata/rec_model_service、OpenAPI） |

- **contracts/metadata/rec_model_service**、**entity_catalog**、**endpoint_catalog**、**OpenAPI rec-model-service.v1.yaml** 以及 Go 侧 **ModelServiceClient** 均归属 **rec-model-service**。
- 若未来为训练工程增加「提交训练任务」等 API，再为 **rec-model-training** 单独建 metadata/OpenAPI 与 endpoint 条目。

### 6.3 迁移状态（已完成）

- 原 **rec-model-engineering-service** 节点已移除。
- **training-pipeline** 及其 L5 已迁至 **rec-model-training** 下；**inference-api**、**go-integration** 已迁至 **rec-model-service** 下。
- **cloud-deployment** 已拆为：**training-deployment** 归 rec-model-training；**inference-deployment** 归 rec-model-service。

---

## 7. 小结

| 问题 | 结论 |
|------|------|
| 实际部署是否有两个服务形态？ | **是**：训练工程（任务/作业 + 训练镜像）与模型服务（常驻推理服务）。 |
| 是否在推荐平台下分离？ | **是**：特性树与服务规划均为 rec-model-training 与 rec-model-service 两个 L3/服务。 |
| 契约与元数据 | 打分契约与 metadata 归属 rec-model-service；训练侧可先无对外 API，后续再为 rec-model-training 增加独立契约。 |
