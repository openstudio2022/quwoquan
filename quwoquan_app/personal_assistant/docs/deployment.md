# Personal Assistant Deployment and Rollback

## Multi-device capability differences

- `mobile`: 权限与算力受限，优先本地轻能力，复杂任务可 hybrid 路由。
- `tablet`: 兼顾本地与远程，intent 类能力建议 hybrid。
- `pc`: 支持 remote-preferred，重任务可转发到 OpenClaw/Mac mini 节点。

## Independent configuration

1. 创建目录：`~/.personal_assistant/`
2. 复制模板：
   - `personal_assistant/config/config.example.json` -> `~/.personal_assistant/config.json`
   - `personal_assistant/config/.env.example` -> `~/.personal_assistant/.env`
3. 填写真实 API key 和网关 token。

## Gateway deployment

- 默认端口：`18181`
- 接口：
  - `GET /v1/skills`
  - `POST /v1/skills/invoke`
  - `POST /v1/run`
- 鉴权：`Authorization: Bearer <PERSONAL_ASSISTANT_GATEWAY_TOKEN>`
- 限流：按 token/IP 每分钟 30 次（内置基础限流）

## Rollback steps

1. 打开 feature flag，切回旧 mock 会话路径。
2. 停止 `AssistantHttpGateway` 对外监听。
3. 保留 `personal_assistant` 代码与配置，不删除历史数据。
4. 恢复后通过 `acceptance_scenarios_test.dart` 与 `acceptance_vm_test.dart` 验证链路。
