# L2 Design：配置与可靠性治理 (`config-and-reliability-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力”需要 `config-source-governance`、`reliability-policy-control` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`config-source-governance`](./config-source-governance/spec.md)：系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实。
- [`reliability-policy-control`](./reliability-policy-control/spec.md)：用 SLO、错误预算、kill-switch 和回滚阈值约束高风险配置与服务发布。

## 3. 端云与数据流

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 配置发布和可靠性状态由平台运维控制面统一裁决
- 决策：配置发布和可靠性状态由平台运维控制面统一裁决。
- 理由：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`config-source-governance`](./config-source-governance/spec.md)、[`reliability-policy-control`](./reliability-policy-control/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 Hosted receipt 是生产发布的唯一可提升事实
- 决策：`prod-hosted` 发布先写入 service-plane 的不可变 receipt，再从同一受控平面回读并校验；本机 `.qwq_output` 或 runner 目录只允许保存 readback cache，不得作为 rollout、rollback 或 readiness 的事实来源。
- receipt：绑定 release manifest、候选 image/config/ContractGraph/adapter digest、CAS generation、gray stage、SLO 与 post-check 摘要、last-good target 和 rollback outcome；`gray-initial → carry-on → full`、`rolled_back` 与 `rollback_failed` 是互斥的状态事实。
- 理由：本机缓存、日志和人工 ref 无法证明托管环境实际应用了候选版本，也无法在多 runner 下可靠阻止陈旧状态提升。
- 被否决方案：只同步本地 ledger 后立即宣称成功、仅凭 operator sidecar 的任意 `receipt:*` 字符串，或把回滚成功与回滚失败折叠为同一状态。
- 约束与影响：Provider Conformance 仅接受 `receipt:hosted:<sha256>` 的 last-good/rollback ref，并由 `stackctl hosted-release-receipt` 从 hosted service plane 拉取、校验 candidate digest 后确认。SSH 凭据、托管平面、真实 Provider/设备或审批缺失时必须失败且不得写 ready。
- 关联要求：`REQ-002`
- 影响 Story：[`reliability-policy-control`](./reliability-policy-control/spec.md)
- 关联验收：`SIT-001`、`GWT-002`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 各领域各自维护 `sys.*` 配置读写与灰度口径。
- 方案 A：配置包版本 + 渐进灰度。
- 高风险配置天然可审计、可回滚。
- 对配置中心的“秒级生效”能力利用不足。
