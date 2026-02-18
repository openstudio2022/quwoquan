# personal-assistant-commercial-v1

## Purpose

个人私人助理（Personal Assistant）商业化 v1 基线能力：在趣我圈内提供可正式对外发布的 AI 原生能力平台，覆盖 App 内对话、知识问答、技能市场治理、渠道适配（Feishu/OpenClaw）、provider 策略路由、SLO 告警、自动降级与灰度发布操作序列。  
本规范作为后续优化、回归与验收的统一基线。

---

## ADDED Requirements

### Requirement: 对外命名与版本规范

系统对外核心 API MUST 使用 `assistent` 前缀语义，版本 MUST 固定为 `/v1/*`（开发阶段但具备正式发布能力）。  
本阶段禁止引入 `/v2/*` 对外路径。

#### Scenario: API 路径一致

- **WHEN** 任意外部系统调用个人私人助理能力
- **THEN** 仅通过 `/v1/assistent/*` 路径访问，不出现 `/v2/*`

#### Scenario: 核心语义前缀一致

- **WHEN** 新增对外核心接口、文档或脚本
- **THEN** 使用 `assistent*` 语义命名，避免与内部实验命名混杂

---

### Requirement: 商业网关能力完整性

系统 SHALL 提供可商用的统一网关，至少包含：providers、skills、runs、stream、sessions、costs、alerts、adapters、channels ingress。

#### Scenario: 基础接口可用

- **WHEN** 访问商业网关
- **THEN** 下列接口可用且返回结构化 JSON：  
  `GET /v1/assistent/providers`  
  `GET /v1/assistent/skills`  
  `POST /v1/assistent/skills/invoke`  
  `POST /v1/assistent/runs`  
  `POST /v1/assistent/runs/stream`  
  `GET /v1/assistent/sessions`  
  `GET /v1/assistent/costs`  
  `GET /v1/assistent/alerts`  
  `GET /v1/assistent/adapters`  
  `POST /v1/assistent/channels/{adapterId}`

#### Scenario: 响应观测字段完整

- **WHEN** 执行 run 或 invoke
- **THEN** 响应包含 `runId`、`traceId`、`degraded`、`errorCode`

在执行 `POST /v1/assistent/runs` 与 `POST /v1/assistent/runs/stream` 时，系统响应观测字段 MUST 除 `runId/traceId/degraded/errorCode` 外，支持关联日志查询信息（如 `sessionId` 与可选 `logExportRef`）。

#### Scenario: run 响应可回溯日志

- **WHEN** 运行一次私人助理问答
- **THEN** 结果可定位到对应 run 聚合日志与 integrations 明细日志

---

### Requirement: ReAct++ 推理规划主循环

系统 SHALL 支持 Plan/Act/Observe/Reflect/Replan 的状态闭环，具备预算、迭代、失败重规划与风险域审慎策略。推理主循环在工具交互时 SHALL 输出可查询交互明细，并与页面访问链路关联：

- 输入快照
- 每次交互（llm/search/cloud_api）请求与响应
- 最终输出结果

#### Scenario: 复杂问题多步规划

- **WHEN** 用户发起涉及检索与综合判断的问题（如出行+天气）
- **THEN** 系统生成多步执行并输出可追踪过程，不退化为单步模板回复

#### Scenario: 失败触发重规划

- **WHEN** 某一步执行失败或证据不足
- **THEN** 系统触发 Reflect/Replan 并选择替代路径

#### Scenario: 问天气全链路可追踪

- **WHEN** 用户提问「深圳天气怎样」
- **THEN** 可查询从页面访问、模型调用、搜索调用到最终答案的完整链路

---

### Requirement: 知识问答策略化输出

知识问答 SHALL 采用策略链（初查 -> 补查 -> 交叉验证 -> 归纳），输出格式 MUST 包含 `结论 + 依据 + 不确定性`。  
知识问答 MUST 默认免订阅可用。

#### Scenario: 高频生活问答

- **WHEN** 用户提问天气、出行、财经、情感、健康、易经等问题
- **THEN** 返回结构化结论并附依据与不确定性说明

---

### Requirement: Skill 商业治理

Skill manifest MUST 包含商业治理字段：`tier`、`channelScopes`、`deviceScopes`、`versionPolicy`、`permissionScopes`、`defaultEnabled`。  
网关层 MUST 执行订阅、渠道、设备与权限约束，不能仅依赖 UI 开关。

#### Scenario: 非授权能力拦截

- **WHEN** 非授权渠道或设备调用某 skill
- **THEN** 网关返回拒绝并带可解释错误码

---

### Requirement: Adapter 服务化与可扩展接入

系统 SHALL 通过 Adapter SPI 接入渠道，不可侵入核心引擎。  
Adapter MUST 支持 verify / ingest / dispatch 生命周期。

#### Scenario: 新渠道快速接入

- **WHEN** 新增渠道适配器
- **THEN** 仅通过 SPI 插件扩展，不修改核心推理执行链路

#### Scenario: Feishu/OpenClaw 首发可用

- **WHEN** 查询 `GET /v1/assistent/adapters`
- **THEN** 至少返回 `feishu` 与 `openclaw`

---

### Requirement: 可配置签名策略（对照 Moltbot）

Adapter verify MUST 支持策略化验签：`none | token | hmac_sha256`。  
在 `hmac_sha256` 模式下 MUST 使用原始请求体参与签名，并进行常量时间比较；可选时间戳窗口防重放。

#### Scenario: 验签失败拦截

- **WHEN** 渠道请求签名不合法或过期
- **THEN** 请求被拒绝，返回鉴权失败

#### Scenario: 验签策略可配置

- **WHEN** 运营切换渠道验签模式
- **THEN** 通过配置生效，无需改代码

---

### Requirement: Provider 级策略路由联动

Provider 路由 MUST 联动成本、延迟、健康状态与 SLO 快照，不得仅按静态优先级。  
运行前 SHOULD 进行 provider 候选评估，运行后 MUST 记录性能结果用于下次路由。

#### Scenario: 渠道感知选路

- **WHEN** 渠道为 app（成本敏感）或外部渠道（时延敏感）
- **THEN** 路由策略输出不同 provider 选择

---

### Requirement: SLO 监控与告警触发

系统 SHALL 提供窗口化 SLO 评估（P95、可用性、错误率）并触发 `warning/critical` 告警。  
告警 MUST 可查询、可审计、可用于灰度门禁。

#### Scenario: SLO 违反触发告警

- **WHEN** provider 指标违反 SLO 阈值
- **THEN** 生成并分发告警，可通过 `GET /v1/assistent/alerts` 查询

---

### Requirement: 告警策略路由与抑制窗口

告警分发 SHALL 支持日志、Webhook、Feishu 机器人三通道。  
系统 MUST 支持告警抑制窗口，防止同类告警风暴。

#### Scenario: 同类告警抑制

- **WHEN** 相同 provider + severity 在短时间重复触发
- **THEN** 根据抑制窗口进行聚合抑制，不重复刷屏

---

### Requirement: 自动降级与人工恢复

当 `critical` 告警触发时，系统 MUST 对异常 provider 执行临时禁用（自动降级），并支持人工恢复接口。

#### Scenario: critical 自动降级

- **WHEN** provider 连续触发 critical 级 SLO 告警
- **THEN** provider 被临时禁用，路由自动避让

#### Scenario: 人工恢复

- **WHEN** 运维确认 provider 已恢复
- **THEN** 可通过 `POST /v1/assistent/providers/{providerId}/recover` 解除临时禁用

---

### Requirement: 成本账本与可追溯审计

系统 MUST 按 run 记录 token 与成本估算，并提供聚合查询；关键动作 MUST 写审计日志（含自动降级/人工恢复）。

#### Scenario: 成本可追踪

- **WHEN** 查询 `GET /v1/assistent/costs`
- **THEN** 可获得 summary 与 recent records

---

### Requirement: 安全与访问控制

网关 MUST 支持 Bearer 鉴权与 ACL 校验，禁止未授权调用关键能力。

#### Scenario: 未授权请求

- **WHEN** 请求缺少或携带无效凭据
- **THEN** 返回 401/403，且不进入执行链路

---

### Requirement: 规范与设计系统约束

涉及 App 侧页面或组件改造时，MUST 遵循项目设计系统与语义规则：`AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`，禁止硬编码视觉常量。

#### Scenario: UI 改造一致性

- **WHEN** 调整助手入口/对话/技能面板
- **THEN** 不出现硬编码颜色、间距、字号与相对路径导入违规

---

### Requirement: 显式标注与开发态回放验收面板

系统 MUST 提供用户可见的显式标注入口（有帮助/没帮助/纠正），并将显式标注事件纳入学习链路。  
开发态 MUST 提供回放面板，用于展示检索计划、策略裁决、轮次轨迹以及显式标注统计分布。

#### Scenario: 显式标注闭环

- **WHEN** 用户在助理回复下点击“有帮助/没帮助/纠正”
- **THEN** 系统记录 `explicitThumb`、`explicitReasonCodes`、`correctionText` 并进入本地学习与 mock 同步链路

#### Scenario: 回放面板统计维度完整

- **WHEN** 在开发态打开助理回放页
- **THEN** 页面可展示按 `原因码`、`domain`、`用户标签` 的显式标注分布，并可见 queryPlan/policyDecision/roundTraces

---

## 运行配置基线（生产强化）

以下配置为商业灰度建议基线（可按环境覆盖）：

- 网关与路由：
  - `PERSONAL_ASSISTENT_ENABLE_API=true`
  - `PERSONAL_ASSISTANT_GATEWAY_TOKEN=...`
- 验签策略：
  - `ASSISTENT_FEISHU_SIGN_MODE=hmac_sha256`
  - `ASSISTENT_FEISHU_SIGN_SECRET=...`
  - `ASSISTENT_FEISHU_MAX_SKEW_SECONDS=300`
  - `ASSISTENT_OPENCLAW_SIGN_MODE=hmac_sha256`
  - `ASSISTENT_OPENCLAW_SIGN_SECRET=...`
  - `ASSISTENT_OPENCLAW_MAX_SKEW_SECONDS=300`
- 告警与降级：
  - `ASSISTENT_ALERT_WEBHOOK_URL=...`
  - `ASSISTENT_ALERT_FEISHU_WEBHOOK=...`
  - `ASSISTENT_ALERT_SUPPRESS_SECONDS=180`
  - `ASSISTENT_ALERT_AUTO_DISABLE_MINUTES=10`

---

## 灰度操作序列（24h）

### 阶段 0：预检（T-30min）

1. 配置核对（token、验签、告警路由、降级时长）
2. 启动应用并确认 `AssistentApiGateway` 已启用
3. 执行静态检查：`flutter analyze lib/main.dart lib/personal_assistant`

### 阶段 1：冒烟（T0-T30min）

1. 查询 adapters/providers/skills
2. 跑一轮 run 与 stream
3. 执行 synthetic alert（warning + critical）
4. 验证 alerts 与 provider runtime state

### 阶段 2：低流量灰度（T30min-T6h）

1. 小流量导入 app + feishu + openclaw
2. 每 30 分钟检查：
   - P95、可用性、错误率
   - 告警数量与抑制效果
   - 自动降级是否触发/是否误触发
   - 成本均值是否在基线范围

### 阶段 3：扩大灰度（T6h-T24h）

1. 逐步提高灰度比例
2. 持续执行 canary 与告警路由检查
3. critical 出现时执行自动降级 + 人工恢复流程

### 阶段 4：收口（T24h）

1. 汇总指标与异常事件
2. 生成灰度结论（继续放量 / 维持 / 回滚）
3. 固化 RCA 与配置调整建议

---

## 灰度实操命令清单（可直接执行）

### 启动前

```bash
flutter analyze lib/main.dart lib/personal_assistant
```

### 商业网关 canary

```bash
bash personal_assistant/scripts/assistent_canary_check.sh "http://127.0.0.1:19191"
```

### 告警路由联调

```bash
bash personal_assistant/scripts/assistent_alert_route_test.sh "http://127.0.0.1:19191" "synthetic_provider"
```

### 渠道链路联调（Feishu/OpenClaw）

```bash
bash personal_assistant/scripts/feishu_openclaw_voice_demo.sh "http://127.0.0.1:19191" "请给出杭州周末出行建议"
```

### 查看关键状态

```bash
curl -s "http://127.0.0.1:19191/v1/assistent/providers"
curl -s "http://127.0.0.1:19191/v1/assistent/alerts"
curl -s "http://127.0.0.1:19191/v1/assistent/costs"
curl -s "http://127.0.0.1:19191/v1/assistent/alerts/config"
```

### 手动恢复被临时禁用的 provider

```bash
curl -s -X POST "http://127.0.0.1:19191/v1/assistent/providers/<providerId>/recover"
```

---

## 灰度回滚阈值（任一满足即回滚）

- 连续 2 个采样窗口：`P95 > 3500ms`
- 连续 2 个采样窗口：`可用性 < 0.97`
- 连续 2 个采样窗口：`错误率 > 0.03`
- 关键渠道不可用持续 >= 10 分钟
- 成本突增超过基线 50% 且持续 30 分钟

---

## 与 Moltbot 对照基线（关键迁移点）

- 验签：采用 `raw body + HMAC + 常量时间比较 + 时间戳窗口`
- 路由：引入健康探测与 SLO 快照参与 provider 选路
- 监控：从快照扩展为告警分发、抑制窗口、自动降级与人工恢复闭环

---

## 本次升级落地更新（2026-02-17）

- 完成统一检索标准化：`unified_retrieval` 返回 `queryPlan/policyDecision/roundTraces`，支持逐步披露与可解释回放。
- 完成“使用即标注 + 显式标注”双轨学习：用户在聊天页可直接进行有帮助/没帮助/纠正，事件进入评分聚合链路。
- 完成双层评分聚合：提供 user 维度与 tag×domain 维度聚合快照。
- 完成开发态回放验收面板：可查看单次 run 轨迹与显式标注统计分布（原因码/domain/用户标签）。
- 完成本地 mock 优先与云端占位切换：`local_mock` 默认可用，`cloud_stub` 保留一键切换扩展位。