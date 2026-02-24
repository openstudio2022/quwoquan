# 进入两服务开发的前置条件（Create 阶段 → Implement）

> 依据 [00_MASTER_DEVELOPMENT_FLOW](../../00_MASTER_DEVELOPMENT_FLOW.md)：进入 **Implement** 前须完成 **Create** 并通过 **G1**。本文为 rec-model-training 与 rec-model-service 的联合审视清单。

---

## 1. G1 卡点（必须全部通过）

| 检查项 | 说明 | 当前状态 | 执行位置 |
|--------|------|----------|----------|
| `make verify-metadata` | metadata 内部一致性（aggregates/entities/projections/entity_catalog） | ✅ 已通过 | quwoquan_service |
| `make codegen-rec-model-python` | 生成 Pydantic 模型与 FastAPI 路由骨架至 rec-model-service/generated | ✅ 已通过 | quwoquan_service |
| `make codegen` | Go 骨架（若项目有）；本平台两服务为 Python，可不生成本平台代码 | 可选 | quwoquan_service |
| `make codegen-app` | 端侧 DTO/Repository（若 App 直连 rec-model-service 再生成） | 按需 | quwoquan_service |

**结论**：G1 已具备。进入 Implement 前在 `quwoquan_service` 下执行一次：

```bash
make verify-metadata
make codegen-rec-model-python
```

---

## 2. 特性树与制品（Create 阶段产出）

| 节点 | spec | design | tasks | acceptance | 说明 |
|------|------|--------|-------|------------|------|
| L1 recommendation-platform | ✅ | ✅ | ✅ | ✅ | [spec](spec.md)、[design](design.md)、[tasks](tasks.md)、[acceptance](acceptance.yaml) |
| L3 rec-model-training | ✅ | — | ✅ | ✅ | 设计见 L1 design；本节点 [spec](rec-model-training/spec.md)、[tasks](rec-model-training/tasks.md)、[acceptance](rec-model-training/acceptance.yaml) |
| L3 rec-model-service | ✅ | — | ✅ | ✅ | [spec](rec-model-service/spec.md)、[readiness](rec-model-service/readiness.md)、[tasks](rec-model-service/tasks.md)、[acceptance](rec-model-service/acceptance.yaml) |

L4/L5 的 acceptance 与 tasks 见各子目录，按 `/opsx-apply` 逐项实施时使用。

---

## 3. 元数据与契约（rec-model-service）

| 制品 | 说明 | 状态 |
|------|------|------|
| contracts/metadata/rec_model_service/ | service、fields、entity、events、storage | ✅ 已就绪 |
| contracts/metadata/_projections/ | learning_events、training_samples、model_registry | ✅ 已就绪 |
| entity_catalog.yaml | ModelScoreRequest、ModelScoreResponse 归属 rec-model-service | ✅ |
| endpoint_catalog | recommendation.score.predict、recommendation.health | ✅ |
| contracts/openapi/rec-model-service.v1.yaml | POST /v1/score、GET /health | ✅ |
| services/rec-model-service/generated/ | codegen 产出（勿手改） | ✅ 已生成 |

详见 [rec-model-service/readiness.md](rec-model-service/readiness.md)。

---

## 4. 元数据与契约（rec-model-training）

| 制品 | 说明 | 状态 |
|------|------|------|
| 无独立 metadata 目录 | 训练侧无对外 HTTP API，不占 entity_catalog 服务位 | — |
| _projections/* | 读 rec_learning_events、写 rec_training_samples、读写 rec_model_registry | ✅ 与 rec-model-service 共用 |
| feature_registry / ModelRegistry | 与 rec-model-service 共用契约，训练产出供推理加载 | ✅ 设计见 L1 design |

训练管线与训练部署的字段、集合、索引以 _projections 为准；Implement 时脚本/任务读写与 YAML 一致即可。

---

## 5. 进入 Implement 时的约定

- **rec-model-training**：按 [rec-model-training/tasks.md](rec-model-training/tasks.md) 及 L4/L5 tasks 实施；每完成一个 task 运行 `make build`（若涉及 Go 工具）及约定脚本/测试。
- **rec-model-service**：按 [rec-model-service/tasks.md](rec-model-service/tasks.md) 及 L4/L5 tasks 实施；每完成一个 task 运行 G2（见主线：build + test-contract；Python 服务需有对应测试与就绪检查）。
- **门禁**：`make gate`（quwoquan_service）在提交前通过；全栈门禁 `make gate-full` 在 Verify 阶段执行。

---

## 6. 审视结论

| 维度 | 是否具备 |
|------|----------|
| G1（verify-metadata + codegen-rec-model-python） | ✅ 已具备 |
| L1 特性 spec/design/tasks/acceptance | ✅ 已具备 |
| L3 两节点 spec/tasks/acceptance | ✅ 已具备 |
| rec-model-service metadata + codegen + readiness | ✅ 已具备 |
| rec-model-training 依赖的 _projections 与契约 | ✅ 已具备 |

**结论**：进入两个服务（rec-model-training、rec-model-service）开发的前置条件已满足，可按 `tasks.md` 与开发流程进入 Implement 阶段。

---

## 7. 两 Agent 完成后的收尾（最终检查 + Go 对接）

> 当 rec-model-service 与 rec-model-training 的并行开发会话均完成后，由本会话执行以下步骤。

### 7.1 最终检查

| 对象 | 检查项 | 参考 |
|------|--------|------|
| **rec-model-service** | inference-api：main.py、POST /v1/score 真实实现、scenario 路由、content_feed 模型或占位、/health；inference-deployment：Dockerfile、docker-compose 条目 | [rec-model-service/tasks.md](rec-model-service/tasks.md) Phase 2/3 |
| **rec-model-training** | 代码落点（如 scripts/ml/）、feature_registry 约定、training-pipeline 与 training-deployment 可跑通或占位 | [rec-model-training/tasks.md](rec-model-training/tasks.md) |
| **门禁** | `make verify-metadata`、`make build`（Go）、rec-model-service 测试（若有） | quwoquan_service |

### 7.2 Go 对接（go-integration，必须在本会话完成）

按 [rec-model-service/go-integration/tasks.md](rec-model-service/go-integration/tasks.md) 顺序：

1. **ModelPredictRequest 增加 Scenario 字段**：在 `runtime/recommendation/scorer.go` 中为 `ModelPredictRequest` 增加 `Scenario string`，与 metadata/OpenAPI 一致；`RemoteModelScorer.ScoreBatch` 请求体带 scenario（如 `content_feed`）。
2. **HTTPModelServiceClient**：实现 `ModelServiceClient` 接口，HTTP POST 到 rec-model-service 的 `/v1/score`，请求/响应与 OpenAPI 一致；可放在 `content-service/internal/infrastructure/recommendation/` 或 `runtime/recommendation/`。
3. **content-service 配置**：config 结构体与 config.yaml 增加 `rec_model_service.url`、`timeout`、`enabled`。
4. **content-service main 装配**：按配置若 enabled 则创建 HTTPModelServiceClient → RemoteModelScorer → CascadeScorer(primary=Remote, fallback=RuleScorer)，`WithScorer(cascade)` 注入 Engine；否则保持仅 RuleScorer。
5. **回退测试**：已有或补充：HTTP 失败/超时时 CascadeScorer 回退 RuleScorer 的测试。

### 7.3 收尾验证

- 运行 `make gate`（quwoquan_service）。
- 若存在 docker-compose：启动 rec-model-service 与 content-service，验证 content-service 可调用 rec-model-service 完成打分（A2/A3 可验证）。

### 7.4 收尾验证结果（已完成）

| 项 | 状态 |
|----|------|
| make verify-metadata | ✅ 通过 |
| make build（runtime + content-service） | ✅ 通过 |
| make gate | ✅ 通过 |
| Go 对接（Scenario、HTTPModelServiceClient、config、CascadeScorer） | ✅ 已实现 |
| content-service 环境变量覆盖 | ✅ REC_MODEL_SERVICE_URL / REC_MODEL_SERVICE_ENABLED / REC_MODEL_SERVICE_TIMEOUT_MS 支持 |

### 7.5 线上反馈→训练 & 部署→内容服务访问

- **线上反馈→训练**：行为上报经 HotPath/BufferedHotPath 写入 Redis；若接入 MongoSink 则写入 `rec_learning_events`。训练管线：`scripts/ml/sample_joiner` 读 `rec_learning_events` 写 `rec_training_samples` → `scripts/ml/train.py` 读样本训练并写 `rec_model_registry` + 模型文件。推理侧从 ModelRegistry/本地路径加载模型。详见 `scripts/ml/README.md`。
- **部署后内容服务访问**：`docker compose up -d redis rec-model-service` 后，content-service 配置 `rec_model_service.url`（如 `http://localhost:18090`）、`enabled: true`，或使用环境变量 `REC_MODEL_SERVICE_URL=http://localhost:18090`、`REC_MODEL_SERVICE_ENABLED=true`，即可使推荐接口调用 rec-model-service 打分；超时/失败时 CascadeScorer 回退 RuleScorer。见 `services/rec-model-service/CONFIG.md`。
