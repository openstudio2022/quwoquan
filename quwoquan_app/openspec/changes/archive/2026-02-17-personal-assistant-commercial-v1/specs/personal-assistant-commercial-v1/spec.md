## ADDED Requirements

### Requirement: 商业化能力规格统一归并

系统 MUST 将个人私人助理商业化 v1 的功能规格、关键设计约束、运行配置基线、灰度操作序列与实操命令清单统一沉淀在 `openspec/specs/personal-assistant-commercial-v1/spec.md`。  
该目录 SHALL 作为后续优化、回归与商用验收的唯一规格基线。

#### Scenario: 规格目录一致

- **WHEN** 团队执行后续私人助理能力演进
- **THEN** 以 `personal-assistant-commercial-v1` 目录为规范入口，不分散到多个临时规格文件

### Requirement: 商业网关与生产强化能力闭环

系统 SHALL 提供 `assistent` 语义前缀与 `/v1/*` 版本路径的统一外部网关，并具备以下生产强化能力闭环：

- SLO 评估（P95/可用性/错误率）
- 告警策略路由（日志/Webhook/Feishu）
- 告警抑制窗口
- provider 自动降级（临时禁用）与人工恢复
- 成本账本与审计追踪

#### Scenario: 进入真实灰度前的门禁检查

- **WHEN** 执行灰度前 canary 与告警路由联调
- **THEN** 需可验证 providers/alerts/costs 状态、自动降级触发与恢复流程可用

### Requirement: 平台化可扩展接入

系统 MUST 通过非侵入式 Adapter SPI 扩展外部渠道能力，至少支持 `verify / ingest / dispatch` 生命周期；  
provider 侧 MUST 支持策略化路由和运行时健康治理，满足规模化推广场景。

#### Scenario: 新渠道接入不改核心链路

- **WHEN** 新增渠道适配器
- **THEN** 通过 SPI 注册接入，不修改核心推理执行循环

## MODIFIED Requirements

### Requirement: chat

聊天能力对个人私人助理调用路径 SHALL 统一走能力网关，响应需包含 `runId/traceId` 以满足端到端观测和排障要求。

#### Scenario: 对话端到端可追踪

- **WHEN** 用户在聊天页触发私人助理运行
- **THEN** 返回结果可关联到网关与工具调用链路

### Requirement: app-global

应用级配置 SHALL 支持个人私人助理商业网关启停、签名策略、告警路由与自动降级参数注入。

#### Scenario: 配置驱动生产强化

- **WHEN** 运维调整签名模式或告警策略
- **THEN** 通过配置生效，无需修改业务代码
