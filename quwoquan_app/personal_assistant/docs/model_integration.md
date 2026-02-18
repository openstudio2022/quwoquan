# Model Integration and Switching

## Xiaomi MiMo (OpenAI-compatible)

`personal_assistant` 默认从独立配置加载模型，不依赖 moltbot 运行时。

优先级如下：

1. `~/.personal_assistant/config.json` + `~/.personal_assistant/.env`
2. 环境变量：
   - `PERSONAL_ASSISTANT_MODEL_PROVIDER`
   - `PERSONAL_ASSISTANT_MODEL_ID`
   - `PERSONAL_ASSISTANT_MODEL_BASE_URL`
   - `PERSONAL_ASSISTANT_MODEL_API_KEY`
3. 可选兼容迁移（默认关闭）：`~/.moltbot/moltbot.json` + `~/.moltbot/.env`

启用兼容迁移：

- `PERSONAL_ASSISTANT_ENABLE_MOLTBOT_COMPAT=true`

Expected provider shape:

- `models.providers.<providerId>.baseUrl`
- `models.providers.<providerId>.apiKey`
- `models.providers.<providerId>.models[].id`
- `agents.defaults.model.primary` for default priority

For MiMo, the common setup is:

- Base URL: `https://api.xiaomimimo.com/v1`
- Endpoint: `POST /chat/completions`

## Runtime behavior

- 若存在远程模型配置，runtime 会注册所有模型并按优先顺序激活。
- runtime 始终保留本地 fallback provider。
- 当前激活远程模型失败时，先尝试下一个远程模型；仍失败则回退本地。

## Model switching API

From `AssistantGateway`:

- `listAvailableModels()`
- `currentModel()`
- `switchModel(String modelRef)`

`modelRef` format:

- `<providerId>/<modelId>`

Example:

- `mimo/mimo-v2-flash`
