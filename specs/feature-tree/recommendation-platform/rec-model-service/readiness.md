# rec-model-service 元数据就绪与开发前检查

> 依据 [00_MASTER_DEVELOPMENT_FLOW](../../../../00_MASTER_DEVELOPMENT_FLOW.md) 与 [00_AGENT_MASTER_SPEC](../../../../00_AGENT_MASTER_SPEC.md)，本服务在进入 Implement 前需完成 metadata 定义并通过 G1。特性树路径：**recommendation-platform/rec-model-service**。

---

## 1. 业务对象与标准接口（已识别并落地）

### 1.1 业务对象

| 对象 | 类型 | 存储 | 生产者 | 消费者 | 元数据位置 |
|------|------|------|--------|--------|------------|
| LearningEvents | 读模型/衍生物 | MongoDB `rec_learning_events` | content-service（MongoSink） | rec-model-service（SampleJoiner） | `_projections/learning_events.yaml` |
| TrainingSamples | 读模型/衍生物 | MongoDB `rec_training_samples` | rec-model-service（SampleJoiner） | rec-model-service（训练脚本） | `_projections/training_samples.yaml` |
| ModelRegistry | 读模型/衍生物 | MongoDB `rec_model_registry` | rec-model-service（训练/导出） | rec-model-service（推理加载） | `_projections/model_registry.yaml` |
| RecommendFeature | 读模型 | MongoDB `rm_recommend_feature` | recommendation-engine | rec-model-service（特征） | 已有 `_projections/recommend_feature.yaml` |
| ModelScoreRequest / ModelScoreResponse | API 契约 DTO | — | content-service 等调用方 | rec-model-service | `rec_model_service/fields.yaml` + `entity_catalog.yaml` |

### 1.2 标准接口

| 接口 | method | path | 说明 | 契约位置 |
|------|--------|------|------|----------|
| 多场景打分 | POST | `/v1/score` | scenario + userId + sessionId + userFeatures + sessionSignals + candidates → scores[] | `rec_model_service/service.yaml`、`contracts/openapi/rec-model-service.v1.yaml` |
| 健康检查 | GET | `/health` | 健康探测 | 同上 |

与 Go 端对齐：`runtime/recommendation/scorer.go` 中 `ModelPredictRequest` / `ModelPredictResponse`；metadata 中已增加 `scenario`、`context` 以支持多场景扩展。

---

## 2. 已完成的元数据与契约

- [x] **rec_model_service/service.yaml**：服务归属、api_routes（POST /v1/score、GET /health）、consumers（content-service、circle-service、user-service）
- [x] **rec_model_service/fields.yaml**：ModelScoreRequest、CandidateInput、ModelScoreResponse、CandidateScore
- [x] **rec_model_service/entity.yaml**、**events.yaml**、**storage.yaml**：占位以满足 `make verify-metadata` 目录校验（本服务无独立存储与领域事件）
- [x] **entity_catalog.yaml**：ModelScoreRequest、ModelScoreResponse（domain: recommendation, service: rec-model-service）
- [x] **_projections/learning_events.yaml**：rec_learning_events 集合与索引
- [x] **_projections/training_samples.yaml**：rec_training_samples 集合与索引
- [x] **_projections/model_registry.yaml**：rec_model_registry 集合与索引
- [x] **contracts/endpoint_catalog.md**：recommendation.score.predict、recommendation.health 及错误归因
- [x] **contracts/openapi/rec-model-service.v1.yaml**：POST /v1/score、GET /health 的请求/响应 schema
- [x] **Python codegen**：`make codegen-rec-model-python` 从同一 metadata 生成 Pydantic 模型与 FastAPI 路由骨架（见下文）

---

## 3. Python codegen（与 App/Go 同源）

- **命令**：在 `quwoquan_service` 下执行 `make codegen-rec-model-python`。
- **输入**：`contracts/metadata/rec_model_service/`（fields.yaml、service.yaml）、`contracts/metadata/_projections/`（learning_events、training_samples、model_registry）。
- **输出**：`services/rec-model-service/generated/`（禁止手改）：
  - `models/request_response.py`：ModelScoreRequest、CandidateInput、ModelScoreResponse、CandidateScore（Pydantic v2）
  - `models/projections.py`：LearningEvent、TrainingSample、ModelRegistryEntry（对应读模型集合）
  - `api/routes.py`：FastAPI APIRouter，POST /v1/score、GET /health 骨架
  - `api/schemas.py`：对上述模型的 re-export。
- **类型映射**（metadata → Python）：string→str，float64/number→float，int64/int→int，bool→bool，object→dict[str, Any]，timestamp→float，ObjectId→str，[]T→list[T]；NOT_NULL 为必填，否则为 Optional（`T | None`）。
- **运行环境**：Python 3.10+，Pydantic v2。

---

## 4. 进入开发前需执行的检查（G1）

按主线 Create 阶段，在进入 Implement 前**必须**通过：

```bash
make verify-metadata          # metadata 内部一致性（quwoquan_service 当前卡点）
make codegen-rec-model-python # Python 模型与 API 骨架（与 App/Go 同源）
# 若项目已接入 codegen：
make codegen                  # Go 侧骨架（本服务为 Python，可能仅校验不生成）
make codegen-app              # 端侧 DTO/Repository（若 App 需直连 rec-model-service 再生成）
```

- **rec-model-service 为 Python 服务**：若当前 codegen 仅针对 Go 聚合/实体，则 `make codegen` 可能不生成本服务代码，但 `make verify-metadata` 应通过（metadata 结构合法）。
- 若存在 **gate 校验**（如 service 必须在 entity_catalog 中有对应实体）：已登记 ModelScoreRequest / ModelScoreResponse，满足“契约实体”归属。

---

## 5. 与 content-service 的契约关系

- content-service 通过 `ModelServiceClient.Predict(ctx, *ModelPredictRequest)` 调用 rec-model-service。
- 请求/响应需与 **contracts/openapi/rec-model-service.v1.yaml** 及 **rec_model_service/fields.yaml** 一致；新增字段时需同步 metadata、OpenAPI 与 Go 结构体。
- 错误码与 **endpoint_catalog.md** 一致：`RECOMMENDATION.USER.*` / `RECOMMENDATION.NETWORK.*` / `RECOMMENDATION.SYSTEM.*`。

---

## 6. 后续 Implement 时注意

- 训练管线读写 **rec_learning_events / rec_training_samples / rec_model_registry** 时，字段与 `_projections/*.yaml` 保持一致。
- 推理 API 实现需满足 Go 侧超时预算（如 30–50ms），超时/失败由 Go CascadeScorer 回退 RuleScorer。
- 新增 scenario 时：更新 `service.yaml` consumers、OpenAPI `scenario` enum、以及特征/模型注册表。
