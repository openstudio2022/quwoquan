# recommendation-service model runtime

推荐模型推理实现。打分只通过 `RecommendationModelRelease` named Reader 暴露；`cmd/api/main.py` 是唯一 API 组合入口，`/health` 仅用于运行探针。

## 本地运行

```bash
cd quwoquan_service
python -m pip install -r services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/requirements.txt
SERVICE_NAME=recommendation-service APP_ENV=alpha PYTHONPATH=services/recommendation-service/cmd/api:services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime uvicorn main:app --host 0.0.0.0 --port 18090
```

`APP_ENV` 只允许 `alpha/beta/gamma/prod`。运行实例必须提供 `CONFIG_ROOT`、`CONFIG_VERSION` 与 `IMAGE_VERSION`，并从只读路径 `<CONFIG_ROOT>/recommendation-service.yaml` 加载唯一有效配置；`CONFIG_VERSION` 必须等于文件内由渲染器生成的语义 sha256。

模型环境变量可覆盖 snapshot 中相应运行值；认证和 capability 绑定由实际部署环境注入。运行代码不得修改环境覆盖或发布状态，在线 guardrail 只输出阻断证据，回滚由 Ops rollout controller 执行。

契约来源：

- `services/recommendation-service/contracts/recommendation/recommendation_model_release/object.yaml`
- `services/recommendation-service/contracts/recommendation/recommendation_model_release/operations.yaml`
- `services/recommendation-service/contracts/recommendation/recommendation_model_release/errors.yaml`
