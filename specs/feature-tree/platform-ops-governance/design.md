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

<a id="dec-002"></a>
### DEC-002 HTTP operation 的 SLO 告警口径只由 ContractGraph 派生
- 决策：`slo.availabilityPercent`（5xx 错误预算）与 `slo.latencyP95Milliseconds` 两个维度的告警只能由 ContractGraph 派生产物承载；手写 PromQL 只承载派生无法表达的口径，且必须在 `handwritten_overlay_manifest.yaml` 登记封闭枚举理由。
- 理由：阈值与契约声明同源后，改契约即改告警，不存在告警与 SLO 各说各话的第二真相源。
- 被否决方案：按域手写等价 PromQL。手写副本会在契约调阈值后静默漂移，正是它被判为「可派生残留」的原因。
- 约束与影响：可派生判定是机械的、没有 allowlist——一条规则消费 `http_server_*` 或契约 record metric、selector 能解析到 operation、形状是 P95 或 5xx 比率，即判定可派生，留在 overlay 由 `verify_contract_alert_overlay.py` BLOCK。业务侧可观测性测试因此断言「契约声明的 SLO 档位有派生告警承载」，不再断言手写告警名。
- 已被本决策替代的手写告警：`AuthChallengeLatencyHigh`（`user.authentication_challenge.SendOtp`，1200ms）、`AuthLoginLatencyHigh`（`user.account_session.Login*`，1500ms）、`ChatConversationCreateLatencyHigh` 与 `ChatGroupCandidateSource*`（`chat.conversation.*`，800ms/500ms 与 99.9% 可用性）。口径未丢失，改由域 coverage 与待商用 coverage 按 SLO 档位承载；`ChatConversationCreateLatencyHigh` 的手写阈值 500ms 与契约声明的 800ms 本就不一致，以契约为准。
- 关联要求：`REQ-001`
- 关联能力：[`observability-and-alerting`](./observability-and-alerting/spec.md)

<a id="dec-003"></a>
### DEC-003 App 依赖 bundle 按平台计划推进 receipt-first/active-last 原子代际
- 决策：同步先冻结显式平台计划及其完整组件闭包，未指定时选双平台。所需平台锁按固定顺序获取，独立平台不争用同一发布槽；共同输入一次冻结，默认双平台分支在私有构建状态内并行，所选闭包全部 readback 成功后才发布。每个平台计划均按在线解析 → fresh 私有 home 完整离线回放 → 封存不可变组件快照 → readback 验证推进，先写不可变 sync receipt，最后原子替换该计划 active pointer；commit readback 必须与本次 attempt 一致。
- 理由：App 打包、UAT 与 canonical launcher 只应依赖本次选择的平台，却仍须消费跨组件一致的代际。平台计划独立不是组件逐个激活；receipt-first/active-last 保证每个可消费代际有完整可重读证据，单平台发布不能覆盖或冒充另一平台和双平台。
- 被否决方案：按组件独立激活、在线解析成功即切换 active、无锁并发同步互相覆盖、以同步顺带更新锁定声明、把 work 目录或未 commit receipt 作为消费面、把 ambiguous commit 静默重试成成功。
- 失败恢复：source/toolchain identity 漂移、在线解析失败、离线回放失败、封存或 readback 失败均保留首个 typed blocker 且 active pointer 保持上一份已验证代际；active 写入已开始但无法证明 commit 结果时以 activation ambiguous 的 typed blocker 报告，禁止自动重试，只能由显式重新同步收敛。锁定声明永不更新，锁漂移是独立 typed blocker，不由同步修复。
- 约束与影响：调用方（打包、UAT、canonical launcher 的交互式 stale 恢复）必须贯穿所需平台，并只消费 committed active readback；source currentness、bundle 覆盖和复用身份均绑定同一平台计划。各平台私有临时目录、工具环境与构建输出不得并行共享可变字节；共享 SDK/生成物仍由其 owner 的锁保护。单平台仅是依赖与开发验收范围，不授予生产全平台资格。
- 可测试观察面：单平台工具调用负例、默认双分支并发、平台锁互斥、独立 active 不覆盖、receipt 摘要篡改及平台复用漂移；记录各 phase 耗时与首个 typed blocker，在现役有界同步 deadline 内完成或失败，不无限排队。失败只保留所选计划的上一代，回滚不改写历史 receipt。
- 调用边界：launcher 侧触发边界（live outer launcher only、pre-projection、one-shot、双 TTY、保留首个 stale blocker）由 [`runtime-config` design DEC-003](../runtime/runtime-config/design.md#dec-003) 拥有，本 DEC 只拥有 sync 事务本身的对象与恢复语义。
- 关联要求：`REQ-005`
- 关联能力：[`config-and-reliability-governance`](./config-and-reliability-governance/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
