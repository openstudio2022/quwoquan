# L1 特性：recommendation-platform（推荐/ML 平台）

## 功能说明

- **定位**：推荐与 ML 平台能力域，下辖**两个 L3 组件**，与 runtime 下的 Go 推荐引擎通过 HTTP 协作：
  - **rec-model-training**（训练集部署工程服务）：对接不同训练场景，样本→数据集→训练→模型注册；部署形态为任务/训练镜像。
  - **rec-model-service**（模型服务）：装载不同模型，暴露 POST /v1/score，对接 Go 业务服务；部署形态为常驻推理服务。
- **服务清单**：计为**两个独立服务**（rec-model-training、rec-model-service），与 content-service、user-service 等并列，开发与运维边界清晰。
- **分离依据**：训练与推理在实际部署上为两种形态（任务/作业 vs 常驻服务），职责、SLA 与契约不同；设计动因与结构见 [design.md](design.md)。

## 与 runtime 的关系

- **runtime**（L1）：推荐引擎（dual-channel-recommendation-engine）通过 HTTP 调用本平台下的 **rec-model-service** 完成 ML 打分；不直接依赖 rec-model-training。
- **本平台**：不归属 runtime，独立部署、独立版本与门禁。

## 约束

- 训练与推理均不写业务库；仅读 rec_learning_events、rec_training_samples、rm_recommend_feature 等。
- 推理 API 需满足 Go 侧超时预算（如 30–50ms），超时或失败时由 Go CascadeScorer 回退 RuleScorer。
- 两 L3 共用 feature_registry、ModelPredictRequest/Response 契约；训练产出与推理加载通过 ModelRegistry + OSS 解耦。

## 适用范围与约束

- **适用**：推荐/ML 场景下「训练（批/任务）」与「推理（常驻服务）」分离的架构；当前模型形态为 LightGBM/规则可回退，场景为 content_feed 等有限 scenario；与 runtime 推荐引擎通过 HTTP 集成、不直接依赖训练侧。
- **不适用/不负责**：非推荐场景（如纯检索、风控模型）的模型服务形态不在本节点约定；按 scenario 拆成多推理服务、训练侧对外暴露「提交训练任务」API 等，由后续特性在对应 L4/L5 的 spec/design/tasks 中说明。
- **前置条件**：ModelRegistry + OSS/TOS 可用；Go 侧已具备 CascadeScorer 与 RuleScorer 兜底；feature_registry 与推理契约已对齐。

## 子节点与验收重点

| L3 | 说明 | 验收重点 |
|----|------|----------|
| rec-model-training | 训练管线 + 训练部署 | 样本→数据集→训练→注册可跑通；feature_registry 与推理侧一致；见其下 L4/L5。 |
| rec-model-service | 推理 API + Go 集成 + 推理部署 | POST /v1/score、延迟与兜底、契约与 metadata 一致；见 [rec-model-service/readiness.md](rec-model-service/readiness.md) 及其下 L4/L5。 |

## 进入开发前置条件

- 进入两服务（rec-model-training、rec-model-service）Implement 前须通过 Create 阶段 G1，并满足特性树与契约就绪。**审视清单与当前状态**见 [preconditions.md](preconditions.md)。

## 验收标准（L1 概要）

- A1：两 L3 边界清晰，训练侧无推理 API 交付责任，推理侧无训练镜像交付责任。
- A2：rec-model-service 推理延迟与可用性满足约定；超时/失败时 Go 侧可回退。
- A7：rec_model_service 契约与 metadata/OpenAPI/endpoint_catalog 一致。
- A8：训练管线与推理 API 各有对应测试与就绪检查；见各 L4/L5 acceptance。
