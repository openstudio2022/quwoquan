# Assistent v1 灰度 24h 观测与回滚阈值模板

## 一、灰度范围

- 灰度时间窗：`____-__-__ __:__` 至 `____-__-__ __:__`（24h）
- 灰度渠道：`app / feishu / openclaw`（勾选）
- 灰度流量比例：`__%`
- 生效配置版本：`v1`

## 二、核心观测指标（每 30 分钟采样）

| 指标 | 目标 | 当前 | 状态 |
|---|---:|---:|---|
| P95 延迟(ms) | <= 2800 |  |  |
| 可用性 | >= 0.985 |  |  |
| 错误率 | <= 0.015 |  |  |
| critical 告警次数 | 0~可控 |  |  |
| provider 自动降级次数 | 0~可控 |  |  |
| run 成本均值(USD) | 基线±20% |  |  |

## 三、必查接口

- `GET /v1/assistent/providers`
- `GET /v1/assistent/alerts`
- `GET /v1/assistent/costs`
- `POST /v1/assistent/runs`
- `POST /v1/assistent/channels/feishu`
- `POST /v1/assistent/channels/openclaw`

## 四、告警与处置

### 告警路由配置核验

- [ ] `GET /v1/assistent/alerts/config` 返回路由信息正常
- [ ] `POST /v1/assistent/alerts/test` 可推送 warning
- [ ] `POST /v1/assistent/alerts/test` 可推送 critical

### critical 处置流程

1. 检查 `GET /v1/assistent/providers` 中 `temporarilyDisabled` 状态
2. 排查 provider 侧异常（网络、配额、超时）
3. 必要时人工恢复：
   - `POST /v1/assistent/providers/{providerId}/recover`
4. 观察 10 分钟窗口指标恢复情况

## 五、回滚阈值（任一满足即回滚）

- 连续 2 个采样窗口 `P95 > 3500ms`
- 连续 2 个采样窗口 `可用性 < 0.97`
- 连续 2 个采样窗口 `错误率 > 0.03`
- 关键渠道（feishu/openclaw）不可用持续 10 分钟
- 成本突增超过基线 50% 且持续 30 分钟

## 六、回滚动作

1. 降低灰度流量到 0%
2. 停止 `AssistentApiGateway` 或切回旧路由
3. 保留告警、成本、审计数据用于复盘
4. 在 24h 内完成 RCA 与修复计划

