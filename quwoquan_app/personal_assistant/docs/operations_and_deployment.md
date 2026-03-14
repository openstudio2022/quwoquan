# 运营与部署手册

> **版本**：v1.2 · **日期**：2026-03-15
> **合并自**：旧版发布 Runbook · 旧版验收清单 · 旧版灰度模板 · deployment.md · model_integration.md

---

## 一、环境配置

### 1.1 独立配置目录

```bash
mkdir -p ~/.personal_assistant
cp personal_assistant/config/config.example.json ~/.personal_assistant/config.json
cp personal_assistant/config/.env.example ~/.personal_assistant/.env
# 填写真实 API key 和网关 token
```

### 1.2 必需环境变量

```bash
# 网关认证
PERSONAL_ASSISTANT_GATEWAY_TOKEN=<secret>

# 模型配置（优先级 1）
PERSONAL_ASSISTANT_MODEL_PROVIDER=mimo
PERSONAL_ASSISTANT_MODEL_ID=mimo-v2-flash
PERSONAL_ASSISTANT_MODEL_BASE_URL=https://api.xiaomimimo.com/v1
PERSONAL_ASSISTANT_MODEL_API_KEY=<key>

# 搜索 provider（至少配置一个）
BRAVE_API_KEY=<key>
PERPLEXITY_API_KEY=<key>

# OpenClaw 集成（可选）
PERSONAL_ASSISTANT_OPENCLAW_BASE_URL=http://...

# 渠道 Adapter 签名（可选）
ASSISTANT_FEISHU_SIGN_MODE=none|token|hmac_sha256
ASSISTANT_FEISHU_SIGN_SECRET=...
ASSISTANT_OPENCLAW_SIGN_MODE=none|token|hmac_sha256
ASSISTANT_OPENCLAW_SIGN_SECRET=...

# 告警（可选）
ASSISTANT_ALERT_WEBHOOK_URL=...
ASSISTANT_ALERT_FEISHU_WEBHOOK=...
ASSISTANT_ALERT_SUPPRESS_SECONDS=300
ASSISTANT_ALERT_AUTO_DISABLE_MINUTES=10

# 商业 API Gateway（可选）
PERSONAL_ASSISTANT_ENABLE_API=true
```

### 1.3 多设备能力差异

| 设备 | 策略 |
|---|---|
| `mobile` | 权限与算力受限，优先本地轻能力，复杂任务可 hybrid 路由 |
| `tablet` | 兼顾本地与远程，intent 类能力建议 hybrid |
| `pc` | 支持 remote-preferred，重任务可转发到 OpenClaw 节点 |

---

## 二、模型接入与切换

### 2.1 配置加载优先级

1. `~/.personal_assistant/config.json` + `~/.personal_assistant/.env`（最高优先级）
2. 环境变量（`PERSONAL_ASSISTANT_MODEL_*`）
3. 项目内 bundled config（`personal_assistant/config/`）
4. 默认本地 fallback provider（最低优先级）

### 2.2 MiMo 模型配置

```json
{
  "models": {
    "providers": {
      "mimo": {
        "baseUrl": "https://api.xiaomimimo.com/v1",
        "apiKey": "<key>",
        "models": [
          {"id": "mimo-v2-flash"}
        ]
      }
    },
    "agents": {
      "defaults": {
        "model": {"primary": "mimo/mimo-v2-flash"}
      }
    }
  }
}
```

### 2.3 模型切换 API

```dart
// 查询可用模型
runtime.listAvailableModels()   // → ["mimo/mimo-v2-flash", ...]

// 当前激活模型
runtime.currentModel()

// 切换模型（格式: <providerId>/<modelId>）
runtime.switchModel("mimo/mimo-v2-flash")
```

### 2.4 降级行为

- 当前激活模型失败 → 尝试下一个已注册模型
- 全部远程失败 → 回退本地 fallback provider
- 结果标记 `degraded=true`

---

## 三、启动流程

```bash
# 1. 启动核心 Gateway（必需）
#    AssistantHttpGateway 监听 18181
flutter run --dart-define=PERSONAL_ASSISTANT_GATEWAY_TOKEN=<token>

# 2. 启动对外 API Gateway（可选）
flutter run --dart-define=PERSONAL_ASSISTANT_ENABLE_API=true \
            --dart-define=PERSONAL_ASSISTANT_GATEWAY_TOKEN=<token>
```

确认 Skill 资产已打包：`assets/personal_assistant/skills/` 目录存在于 App bundle。

---

## 四、发布前验收检查清单

### 构建与启动

- [ ] App 以 `PERSONAL_ASSISTANT_ENABLE_API=true` 编译通过
- [ ] `AssistantApiGateway` 在端口 `19191` 正常启动
- [ ] `GET /v1/assistant/adapters` 返回至少 `feishu` 和 `openclaw`

### 安全与治理

- [ ] Bearer Token 验证在设置 `PERSONAL_ASSISTANT_GATEWAY_TOKEN` 时生效
- [ ] ACL 拒绝格式错误的 actor/resource/action 请求
- [ ] run 和 invoke 流程写入审计日志

### 核心 API

- [ ] `GET /v1/assistant/providers` 返回 LLM/搜索 provider 元数据
- [ ] `GET /v1/assistant/skills?channel=app` 返回受治理的 Skill 列表
- [ ] `POST /v1/assistant/skills/invoke` 返回 `runId/traceId` 和结果 envelope
- [ ] `POST /v1/assistant/runs` 返回 `runId/traceId/finalText/degraded/errorCode`
- [ ] `POST /v1/assistant/runs/stream` 流式输出 trace 事件和最终 payload
- [ ] `GET /v1/assistant/sessions` 返回已持久化会话摘要

### 渠道 Adapter

- [ ] `POST /v1/assistant/channels/feishu` 解析 webhook 并分发响应 envelope
- [ ] `POST /v1/assistant/channels/openclaw` 解析 OpenClaw payload 并分发
- [ ] 配置签名时 Adapter 验证能拒绝无效签名/token

### 费用与可观测性

- [ ] 每次 run 创建 `AssistantCostLedger` 记录
- [ ] `GET /v1/assistant/costs` 返回摘要和近期记录
- [ ] 所有 run/invoke 响应包含 `runId` 和 `traceId`

### 端到端场景

- [ ] App 文字问答流程成功返回知识类答案
- [ ] 飞书 webhook 文字 → Assistant run → adapter dispatch 流程成功
- [ ] OpenClaw ingress → Assistant run → dispatch 流程成功
- [ ] Provider 降级路径仍能生成安全 fallback 回复

---

## 五、功能冒烟测试

```bash
# 1. 基础接口
curl "http://127.0.0.1:19191/v1/assistant/providers"
curl "http://127.0.0.1:19191/v1/assistant/skills?channel=app"
curl -X POST "http://127.0.0.1:19191/v1/assistant/runs" -d '...'
curl -N "http://127.0.0.1:19191/v1/assistant/runs/stream" -d '...'
curl "http://127.0.0.1:19191/v1/assistant/costs"
curl "http://127.0.0.1:19191/v1/assistant/alerts"

# 2. 一键 canary 脚本
bash personal_assistant/scripts/assistant_canary_check.sh

# 3. 告警路由测试
bash personal_assistant/scripts/assistant_alert_route_test.sh
```

---

## 六、灰度发布观测（24h 模板）

### 灰度配置

| 配置项 | 值 |
|---|---|
| 灰度时间窗 | `____-__-__ __:__` 至 `____-__-__ __:__`（24h）|
| 灰度渠道 | `app / feishu / openclaw`（勾选适用项）|
| 流量比例 | `__%` |
| 配置版本 | `v1` |

### 核心观测指标（每 30 分钟采样）

| 指标 | 目标 | 当前 | 状态 |
|---|---:|---:|---|
| P95 延迟 (ms) | <= 2800 | | |
| 可用性 | >= 0.985 | | |
| 错误率 | <= 0.015 | | |
| critical 告警次数 | 0~可控 | | |
| provider 自动降级次数 | 0~可控 | | |
| run 成本均值 (USD) | 基线±20% | | |

### 必查接口

```bash
GET  /v1/assistant/providers
GET  /v1/assistant/alerts
GET  /v1/assistant/costs
POST /v1/assistant/runs
POST /v1/assistant/channels/feishu
POST /v1/assistant/channels/openclaw
```

### 告警处置

当 critical 触发：
1. 检查 `GET /v1/assistant/providers` 中 `temporarilyDisabled` 状态
2. 排查 provider 侧异常（网络、配额、超时）
3. 必要时手动恢复：`POST /v1/assistant/providers/{providerId}/recover`
4. 观察 10 分钟指标恢复情况

---

## 七、回滚阈值与流程

### 回滚触发条件（满足任一即回滚）

- 连续 2 个采样窗口 `P95 > 3500ms`
- 连续 2 个采样窗口 `可用性 < 0.97`
- 连续 2 个采样窗口 `错误率 > 0.03`
- 关键渠道（feishu/openclaw）不可用持续 10 分钟
- 成本突增超过基线 50% 且持续 30 分钟

### 回滚步骤

```bash
# 1. 降低灰度流量到 0%

# 2a. 停止对外 API Gateway
#     停止 AssistantApiGateway，或

# 2b. 回退核心 Gateway
#     停止 AssistantHttpGateway，切回旧路由

# 3. 保留审计、成本、告警数据（用于复盘）

# 4. 验证回退后链路
flutter test test/acceptance_scenarios_test.dart
flutter test test/acceptance_vm_test.dart

# 5. 24h 内完成 RCA 与修复计划
```
