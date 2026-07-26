# recommendation-service 运行配置

配置键与默认值来自服务 `config/schema.yaml`，四环境差异与 secret reference 来自 `environments/<env>/config.yaml`。`stackctl package` 生成唯一只读有效配置；Ops 不再复制服务配置。

| 变量 | 说明 |
|---|---|
| `APP_ENV` | `alpha`、`beta`、`gamma` 或 `prod` |
| `SERVICE_NAME` | 必须为 `recommendation-service` |
| `CONFIG_ROOT` | 包含 `<service>.yaml` 的只读有效配置根 |
| `CONFIG_VERSION` | 排除自引用 version 字段后的有效配置语义摘要 `sha256:<digest>`，由 package 派生 |
| `IMAGE_VERSION` | 镜像制品 digest/版本，由发布过程注入 |
| `REC_SERVICE_HTTP_ADDR` | HTTP 监听地址覆盖 |
| `REC_MODEL_CONTENT_FEED_PATH` | content feed 模型路径覆盖 |
| `REC_MODEL_CIRCLE_DISCOVERY_PATH` | circle discovery 模型路径覆盖 |
| `REC_MODEL_FRIEND_SUGGESTION_PATH` | friend suggestion 模型路径覆盖 |

运行路径固定为：

```text
<CONFIG_ROOT>/recommendation-service.yaml
```

文件缺失、文件内语义摘要与 `CONFIG_VERSION` 不匹配、镜像版本越界或环境名非法时启动失败。服务不得回退旧分层配置路径，也不得修改环境真相源或 rollout 状态。
