# API 与集成指南

> **版本**：v1.2 · **日期**：2026-03-15
> **合并自**：OpenClaw/飞书接入说明 · 旧版 v1 API 合同 · 旧版商业化规格 · Adapter SPI 说明

---

## 一、架构概述

当前对外发布与集成契约统一收口到 `AssistantApiGateway`：

| Gateway | 用途 | 默认端口 | 当前对外端点前缀 |
|---|---|---|---|
| `AssistantApiGateway` | 外部集成、费用计量、审计、渠道接入 | `19191` | `/v1/assistant/` |

说明：
- `AssistantGateway` 是端侧应用层入口，不再作为当前推荐的外部 HTTP 契约说明主轴。
- 对外文档、脚本、门禁与验收默认都以 `/v1/assistant/*` 为准。

核心组件：
- `AssistantApiGateway`：发布级 HTTP/SSE API
- `AssistantProviderRegistry`：LLM/搜索/嵌入 provider 元数据
- `AssistantCostLedger`：每轮 token 和费用记录
- `AssistantAuthAcl` + `AssistantAuditLogger`：访问控制与审计
- `AssistantAdapterRuntime`：渠道 Adapter SPI 运行时

---

## 二、认证

所有端点支持可选 Bearer Token 鉴权：

```
Env: PERSONAL_ASSISTANT_GATEWAY_TOKEN=<secret>
Header: Authorization: Bearer <token>
```

未设置时，网关为公开访问（开发/内网场景）。

限流：默认 30 请求/分钟（每 token/IP）。超限返回 HTTP `429`。

---

## 三、对外 API 端点（AssistantApiGateway, port 19191）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/assistant/providers` | 列出 LLM/搜索 provider 元数据 |
| `POST` | `/v1/assistant/providers/{id}/recover` | 手动恢复降级的 provider |
| `GET` | `/v1/assistant/models` | 查询当前/可选模型列表 |
| `POST` | `/v1/assistant/models/select` | 切换当前模型或模型集合 |
| `GET` | `/v1/assistant/costs` | 查询费用统计 |
| `GET` | `/v1/assistant/alerts` | 列出最近 SLO 告警 |
| `GET` | `/v1/assistant/alerts/config` | 查询告警配置 |
| `POST` | `/v1/assistant/alerts/test` | 触发测试告警 |
| `GET` | `/v1/assistant/skills?channel=app` | 列出 Skill 列表 |
| `GET` | `/v1/assistant/sessions` | 会话列表 |
| `POST` | `/v1/assistant/skills/invoke` | Skill 调用 |
| `POST` | `/v1/assistant/runs` | 单轮 run API |
| `POST` | `/v1/assistant/runs/stream` | SSE streaming run |
| `GET` | `/v1/assistant/adapters` | 列出已注册 adapter 插件 |
| `POST` | `/v1/assistant/channels/{adapterId}` | Adapter 入口（feishu/openclaw） |

### POST /v1/assistant/runs 请求体

```json
{
  "sessionId": "assistant",
  "userId": "u1",
  "channel": "app",
  "traceId": "trace_123",
  "deviceProfile": "mobile",
  "maxIterations": 8,
  "messages": [
    {"role": "user", "content": "请帮我做杭州周末出行规划"}
  ]
}
```

### 错误契约

| HTTP 状态码 | errorCode | 含义 |
|---|---|---|
| `401` | `unauthorized` | Token 无效 |
| `403` | `forbidden` | ACL 拒绝 |
| `404` | `not_found` | 资源不存在 |
| `429` | `rate_limited` | 请求过于频繁 |
| `500` | `internal_error` | 服务内部错误 |

---

## 四、启动配置

```bash
# 启用对外 API Gateway
PERSONAL_ASSISTANT_ENABLE_API=true

# Bearer Token（可选）
PERSONAL_ASSISTANT_GATEWAY_TOKEN=<secret>

# Feishu 适配器签名
ASSISTANT_FEISHU_SIGN_MODE=none|token|hmac_sha256
ASSISTANT_FEISHU_SIGN_SECRET=...

# OpenClaw 适配器签名
ASSISTANT_OPENCLAW_SIGN_MODE=none|token|hmac_sha256
ASSISTANT_OPENCLAW_SIGN_SECRET=...

# OpenClaw 网关地址（PA → OpenClaw 反向调用）
PERSONAL_ASSISTANT_OPENCLAW_BASE_URL=http://...
```

---

## 五、Adapter SPI

Adapter SPI 实现渠道无侵入集成（飞书、OpenClaw 及未来渠道）。

### 核心接口

```dart
abstract class AssistantAdapterSpi {
  String get adapterId;
  
  // 验证来源签名
  Future<bool> verify(Map<String, String> headers, String rawBody);
  
  // 解析来源事件为标准化格式
  Future<SourceEvent> ingest(Map<String, String> headers, String rawBody);
  
  // 将响应分发回渠道（文本/卡片/流）
  Future<void> dispatch(SourceEvent sourceEvent, ResponseEnvelope response);
}
```

### AssistantAdapterRuntime

```dart
// 解析来源请求
final event = await adapterRuntime.parseIncoming(adapterId, headers, rawBody);

// 分发响应
await adapterRuntime.dispatch(adapterId, event, responseEnvelope);
```

**集成规则**：
- 核心引擎不直接 import 渠道 SDK
- Adapter 负责签名验证并转换为标准化事件
- 响应可以是 text/card/stream，由 Adapter 决定

---

## 六、集成模式

### OpenClaw 集成

```
1. OpenClaw GET /v1/assistant/skills → 同步可用 Skill 列表
2. OpenClaw 注册远程工具（使用 skill 元数据）
3. 用户请求时 OpenClaw POST /v1/assistant/skills/invoke
4. OpenClaw 将 message/data 渲染到渠道 UI
5. 可订阅 POST /v1/assistant/runs/stream 实现逐步 trace 渲染
```

### 飞书集成

```
1. 飞书 bot 接收用户命令
2. 命令路由器调用 OpenClaw（或直接调本 Gateway）
3. Gateway 执行 Skill 并返回标准化 JSON
4. 飞书 bot 将文本/卡片发回当前会话
```

---

## 七、快速示例

```bash
# 列出所有 Skill
curl "http://127.0.0.1:19191/v1/assistant/skills?channel=app"

# 执行知识问答 Skill
curl -X POST "http://127.0.0.1:19191/v1/assistant/skills/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "knowledge_qa",
    "channel": "app",
    "deviceProfile": "mobile",
    "arguments": {
      "toolArgs": {"query": "台积电主要供应商有哪些"}
    }
  }'

# 流式会话
curl -N -X POST "http://127.0.0.1:19191/v1/assistant/runs/stream" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "s1",
    "deviceProfile": "mobile",
    "messages": [{"role": "user", "content": "深圳今天天气"}]
  }'
```

可用脚本：
- `personal_assistant/scripts/list_skills.sh`
- `personal_assistant/scripts/run_chat_turn.sh`
- `personal_assistant/scripts/feishu_openclaw_voice_demo.sh`
