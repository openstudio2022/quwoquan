# recommendation-service 配置与运行

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `APP_ENV` | 运行态：`dev` / `integration` / `prod` | `dev` |
| `SERVICE_NAME` | 服务名，必须为 `recommendation-service`（若设置） | - |
| `CONFIG_VERSION` | 配置版本（`integration/prod` 必填） | - |
| `IMAGE_VERSION` | 镜像版本（`integration/prod` 必填） | - |
| `CONFIG_ROOT` | 配置根目录（`integration/prod` 必填） | - |
| `PYTHONUNBUFFERED` | 建议设为 `1`，便于日志输出 | - |
| `AUTH_JWT_SECRET` | 服务身份 JWT HMAC 密钥 | 必填 |
| `AUTH_JWT_ISSUER` | 服务身份 JWT issuer | 必填 |
| `AUTH_JWT_AUDIENCE` | 服务身份 JWT audience | 必填 |
| `AUTH_JWT_TOKEN_VERSION` | 服务身份 token 版本 | 必填 |
| `REC_MODEL_CONTENT_FEED_PATH` | content_feed 模型文件路径（可选；未设置时使用规则打分） | - |
| `REC_MODEL_CIRCLE_DISCOVERY_PATH` | circle_discovery 模型路径（可选） | - |
| `REC_MODEL_FRIEND_SUGGESTION_PATH` | friend_suggestion 模型路径（可选） | - |

## 本地运行

```bash
cd services/rec-model-service
pip install -r requirements.txt
SERVICE_NAME=recommendation-service APP_ENV=dev uvicorn main:app --host 0.0.0.0 --port 8000
```

- POST `/internal/v1/recommendation/model-releases:score`：打分，请求体与权限见
  `contracts/metadata/recommendation/model_release/service.yaml`
- POST `/internal/v1/recommendation/model-releases:batch-score`：批量打分
- GET /health：健康检查
- 配置契约不满足时，服务启动立即失败（fail-fast）

## Docker

```bash
# 在 quwoquan_service 根目录
docker compose up -d rec-model-service
curl http://localhost:18090/health
```

## 与 content-service 联调

content-service 配置中设置：

```yaml
rec_model_service:
  url: "http://rec-model-service:8000"   # 同网内 Docker 服务名
  timeout_ms: 50
  enabled: true
```

或本地联调时 `url: "http://localhost:18090"`。

content-service 支持环境变量覆盖（无需改 config.yaml）：`REC_MODEL_SERVICE_URL`、`REC_MODEL_SERVICE_ENABLED=true`、`REC_MODEL_SERVICE_TIMEOUT_MS`，便于在 Docker 或 CI 中启用模型打分。
