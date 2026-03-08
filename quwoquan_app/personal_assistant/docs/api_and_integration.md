# API 与集成指南

> **版本**：v1.1 · **日期**：2026-03-07
> **合并自**：openclaw_feishu_integration.md · assistent_v1_api_contract.md · assistent_v1_commercial_spec.md · assistent_adapter_spi.md

---

## 一、架构概述

小趣私人助理通过两个独立 Gateway 对外暴露能力：

| Gateway | 用途 | 默认端口 | 端点前缀 |
|---|---|---|---|
| `AssistantGateway`（核心运行时） | 直接驱动 ReAct 执行 | `18181` | `/v1/` |
| `AssistentApiGateway`（商业 API） | 外部集成、费用计量、审计 | `19191` | `/v1/assistent/` |

核心组件：
- `AssistentApiGateway`：发布级 HTTP/SSE API
- `AssistentProviderRegistry`：LLM/搜索/嵌入 provider 元数据
- `AssistentCostLedger`：每轮 token 和费用记录
- `AssistentAuthAcl` + `AssistentAuditLogger`：访问控制与审计
- `AssistentAdapterRuntime`：渠道 Adapter SPI 运行时

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

## 三、核心 API 端点（AssistantGateway, port 18181）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/skills` | 列出所有 Skill 元数据 |
| `POST` | `/v1/skills/invoke` | 按 skill_id 执行单个 Skill |
| `POST` | `/v1/run` | 执行一轮 ReAct 会话 |
| `POST` | `/v1/run/stream` | 执行一轮，SSE 流式 trace 输出 |
| `GET` | `/v1/sessions` | 列出已持久化的会话 |
| `GET` | `/v1/sessions/:sessionId` | 查询单个会话详情/摘要 |

### POST /v1/run 请求体

```json
{
  "sessionId": "assistant",
  "userId": "u1",
  "channel": "app",
  "deviceProfile": "mobile",
  "messages": [
    {"role": "user", "content": "帮我查杭州本周天气"}
  ]
}
```

### POST /v1/run 响应体

```json
{
  "runId": "1730000000000_assistant",
  "traceId": "trace_123",
  "finalText": "...（用户可读 Markdown）",
  "degraded": false,
  "errorCode": null,
  "traces": []
}
```

---

## 四、商业 API 端点（AssistentApiGateway, port 19191）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/assistent/providers` | 列出 LLM/搜索 provider 元数据 |
| `POST` | `/v1/assistent/providers/{id}/recover` | 手动恢复降级的 provider |
| `GET` | `/v1/assistent/costs` | 查询费用统计 |
| `GET` | `/v1/assistent/alerts` | 列出最近 SLO 告警 |
| `GET` | `/v1/assistent/alerts/config` | 查询告警配置 |
| `POST` | `/v1/assistent/alerts/test` | 触发测试告警 |
| `GET` | `/v1/assistent/skills?channel=app` | 列出商业级 Skill 列表 |
| `GET` | `/v1/assistent/sessions` | 会话列表 |
| `POST` | `/v1/assistent/skills/invoke` | 商业 Skill 调用 |
| `POST` | `/v1/assistent/runs` | 商业 run API |
| `POST` | `/v1/assistent/runs/stream` | 商业 SSE streaming run |
| `GET` | `/v1/assistent/adapters` | 列出已注册 adapter 插件 |
| `POST` | `/v1/assistent/channels/{adapterId}` | Adapter 入口（feishu/openclaw） |

### POST /v1/assistent/runs 请求体

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

## 五、启动配置

```bash
# 启用商业 API Gateway
PERSONAL_ASSISTENT_ENABLE_API=true

# Bearer Token（可选）
PERSONAL_ASSISTANT_GATEWAY_TOKEN=<secret>

# Feishu 适配器签名
ASSISTENT_FEISHU_SIGN_MODE=none|token|hmac_sha256
ASSISTENT_FEISHU_SIGN_SECRET=...

# OpenClaw 适配器签名
ASSISTENT_OPENCLAW_SIGN_MODE=none|token|hmac_sha256
ASSISTENT_OPENCLAW_SIGN_SECRET=...

# OpenClaw 网关地址（PA → OpenClaw 反向调用）
PERSONAL_ASSISTANT_OPENCLAW_BASE_URL=http://...
```

---

## 六、Adapter SPI

Adapter SPI 实现渠道无侵入集成（飞书、OpenClaw 及未来渠道）。

### 核心接口

```dart
abstract class AssistentAdapterSpi {
  String get adapterId;
  
  // 验证来源签名
  Future<bool> verify(Map<String, String> headers, String rawBody);
  
  // 解析来源事件为标准化格式
  Future<SourceEvent> ingest(Map<String, String> headers, String rawBody);
  
  // 将响应分发回渠道（文本/卡片/流）
  Future<void> dispatch(SourceEvent sourceEvent, ResponseEnvelope response);
}
```

### AssistentAdapterRuntime

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

## 七、集成模式

### OpenClaw 集成

```
1. OpenClaw GET /v1/skills → 同步可用 Skill 列表
2. OpenClaw 注册远程工具（使用 skill 元数据）
3. 用户请求时 OpenClaw POST /v1/skills/invoke
4. OpenClaw 将 message/data 渲染到渠道 UI
5. 可订阅 POST /v1/run/stream 实现逐步 trace 渲染
```

### 飞书集成

```
1. 飞书 bot 接收用户命令
2. 命令路由器调用 OpenClaw（或直接调本 Gateway）
3. Gateway 执行 Skill 并返回标准化 JSON
4. 飞书 bot 将文本/卡片发回当前会话
```

---

## 八、快速示例

```bash
# 列出所有 Skill
curl "http://127.0.0.1:18181/v1/skills"

# 执行知识问答 Skill
curl -X POST "http://127.0.0.1:18181/v1/skills/invoke" \
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
curl -N -X POST "http://127.0.0.1:18181/v1/run/stream" \
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
