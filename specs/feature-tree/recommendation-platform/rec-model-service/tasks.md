# 开发任务：rec-model-service（L3）

**开发状态**：Implement 已完成。Go 集成、Python 推理 API、Docker 与 docker-compose 已就绪；`make build`、`make test`、`make gate` 通过。

---

## 当前交付任务（L4 汇总）

- [x] inference-api：POST /v1/score、scenario 路由、模型加载见 [inference-api/tasks.md](inference-api/tasks.md)
- [x] go-integration：HTTP 契约、ModelServiceClient、CascadeScorer 兜底见 [go-integration/tasks.md](go-integration/tasks.md)
- [x] inference-deployment：推理镜像、docker-compose/K8s/PAI-EAS 见 [inference-deployment/tasks.md](inference-deployment/tasks.md)
- [x] 契约与 [readiness.md](readiness.md) 一致；G1（verify-metadata、codegen-rec-model-python）已通过后再手写业务逻辑
- [x] 门禁：make gate 通过；就绪检查与 L4/L5 acceptance 满足

---

## 开发任务清单（按执行顺序，供 /opsx-apply 使用）

依赖顺序：Go 契约与 content-service 装配 → Python 推理 API → 推理部署与联调。

### Phase 1：go-integration（Go 契约与 content-service 装配）

| # | 任务 | 产出/验收 |
|---|------|-----------|
| 1 | ModelPredictRequest 增加 Scenario 字段 | ✅ `runtime/recommendation/scorer.go` 与 metadata/OpenAPI 一致；RemoteModelScorer 请求体带 scenario |
| 2 | 实现 HTTPModelServiceClient | ✅ content-service/internal/infrastructure/recommendation/http_model_client.go |
| 3 | content-service 配置 | ✅ configs/config.yaml rec_model_service.url、timeout_ms、enabled |
| 4 | content-service main 装配 CascadeScorer | ✅ main.go 按配置 WithScorer(cascade)，scenario=content_feed |
| 5 | 回退测试 | ✅ TestHTTPModelServiceClient_Predict_Unreachable、TestCascadeScorer_FallbackWhenHTTPClientFails |

### Phase 2：inference-api（Python 推理服务）

| # | 任务 | 产出/验收 |
|---|------|-----------|
| 6 | FastAPI 应用入口 | ✅ main.py，挂载 api/score 路由；POST /v1/score、GET /health |
| 7 | 请求校验与 scenario 路由 | ✅ api/score.py 按 scenario 分发至 ContentFeedScorer |
| 8 | content_feed 模型加载与推理 | ✅ models/content_feed.py 规则打分占位 |
| 9 | 特征解析 | ✅ features/transformer.py build_candidate_features |
| 10 | ModelRegistry 同步 | ✅ registry.py get_model_path 占位；可选 REC_MODEL_*_PATH |
| 11 | 接口测试 | ✅ tests/test_api.py /v1/score、/health |

### Phase 3：inference-deployment

| # | 任务 | 产出/验收 |
|---|------|-----------|
| 12 | rec-model-service Dockerfile | ✅ services/rec-model-service/Dockerfile，健康检查 |
| 13 | docker-compose 集成 | ✅ docker-compose.yaml rec-model-service:18090 |
| 14 | 环境变量与 config 文档 | ✅ CONFIG.md |
| 15 | 联调验收 | ✅ make gate 通过；docker-compose up 后 curl :18090/health 可验证 |

---

## 搁置任务（带规划）

- **PAI-EAS/火山推理部署脚本**：搁置原因：当前以 docker-compose 联调即可满足；计划在「云上推理部署」需求明确时重启；承接：inference-deployment 或新建 L5。

## 未来演进任务

- **多 scenario 完整实现**：circle_discovery、friend_suggestion 模型与路由占位后可逐步补齐；与 L1 design 中「多场景」一致。
- **双塔/深度模型**：见 L1 [tasks.md](../tasks.md) 未来演进任务；契约保持 POST /v1/score 稳定。
