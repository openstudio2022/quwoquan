# L3 组件：rec-model-service（模型服务）

## 功能说明

- **定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
- **职责**：多场景推理 API（POST /v1/score、scenario 路由）、模型加载（从 ModelRegistry/OSS）、与 Go 集成（HTTP 契约、CascadeScorer 兜底）；部署形态为**常驻在线服务**（FastAPI）。
- **技术栈**：Python（FastAPI、LightGBM）；与 rec-model-training 共用 feature_registry、ModelRegistry 契约。

## 与现有系统关系

- **L1**：recommendation-platform（推荐/ML 平台）
- **本节点 L3**：rec-model-service；与 runtime 下的 dual-channel-recommendation-engine 通过 HTTP 集成，上游训练由 rec-model-training 产出模型。

## 子节点（L4）

| L4 | 说明 |
|----|------|
| inference-api | POST /v1/score、scenario 路由、多场景模型加载与推理 |
| go-integration | HTTP 契约、ModelServiceClient、CascadeScorer 兜底 |
| inference-deployment | 推理镜像、docker-compose/K8s/PAI-EAS、与 content-service 联调 |

## 约束

- 请求/响应与 Go ModelPredictRequest/ModelPredictResponse 契约一致。
- 推理延迟满足 Go 侧预算（如 30–50ms）；超时或失败时 Go CascadeScorer 回退 RuleScorer。

## 验收标准（概要）

- A1：POST /v1/score scenario=content_feed 返回正确 scores。
- A2：推理延迟满足约定。
- A3：模型服务不可用时 Go 侧 CascadeScorer 回退。
- A7：契约与 metadata/OpenAPI 一致。
- A8：推理 API 与 Go 集成有测试；见 [readiness.md](readiness.md)。
