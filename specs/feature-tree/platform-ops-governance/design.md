# L1 Design：platform-ops-governance（运维横切） (`platform-ops-governance`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。

## 2. 领域模型与所有权

- authoritative ownership：拥有平台配置发布、可靠性策略、观测告警、运维审计与生产准出证据的生命周期和治理决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- 上下游只通过公开 command、query、projection 或 event 交换事实。

## 4. 架构与数据流

- [`commercial-readiness-risk-closure`](./commercial-readiness-risk-closure/spec.md)：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- [`config-and-reliability-governance`](./config-and-reliability-governance/spec.md)：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- [`observability-and-alerting`](./observability-and-alerting/spec.md)：建立日志、指标、追踪与告警的统一治理能力，覆盖云侧服务、端侧运行时和控制面配置发布链路。
- [`security-privacy-audit`](./security-privacy-audit/spec.md)：统一发布前与运营期的权限、隐私、审计和供应链检查
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 运行证据、配置发布与告警状态由平台运维控制面聚合
- 决策：运行证据、配置发布与告警状态由平台运维控制面聚合。
- 理由：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 生产审批 authority 与 rollout ledger、timing ledger 分离：webhook 接收面只 append event，审批 readback 只按 repository/run/head/candidate/environment 查询；部署编排只消费 readback，不拥有 reviewer decision。
- 私有仓当前套餐下该 authority 是外部硬门，不是 GitHub 原生 branch/environment protection 的副本或兼容层。任何用户可见或机器回执必须保留 `nativeProtection=false`。
- 关联要求：`REQ-001`
- 关联能力：[`commercial-readiness-risk-closure`](./commercial-readiness-risk-closure/spec.md)、[`config-and-reliability-governance`](./config-and-reliability-governance/spec.md)、[`observability-and-alerting`](./observability-and-alerting/spec.md)、[`security-privacy-audit`](./security-privacy-audit/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
