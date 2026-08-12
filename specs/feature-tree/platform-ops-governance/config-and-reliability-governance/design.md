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
- 影响 Story：本能力的全部直属 Story。
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 Hosted receipt 是生产发布的唯一可提升事实
- 决策：`prod-hosted` 发布先写入 service-plane 的不可变 receipt，再从同一受控平面回读并校验；本机 `.qwq_output` 或 runner 目录只允许保存 readback cache，不得作为 rollout、rollback 或 readiness 的事实来源。
- receipt：绑定 release manifest、`campaignId`、候选 image/config/ContractGraph/adapter digest、`allocationKeyId`、`subjectKind`、阶段 audience 摘要、CAS generation、`canary → 5 → 20 → 50 → 100` stage、SLO 与 post-check 摘要、last-good target 和 rollback outcome；每个阶段、`rolled_back` 与 `rollback_failed` 都是独立且互斥的状态事实。
- 理由：本机缓存、日志和人工 ref 无法证明托管环境实际应用了候选版本，也无法在多 runner 下可靠阻止陈旧状态提升。
- 被否决方案：只同步本地 ledger 后立即宣称成功、仅凭 operator sidecar 的任意 `receipt:*` 字符串，或把回滚成功与回滚失败折叠为同一状态。
- 约束与影响：Provider Conformance 仅接受 `receipt:hosted:<sha256>` 的 last-good/rollback ref，并由 `stackctl hosted-release-receipt` 从 hosted service plane 拉取、校验 candidate digest 后确认。SSH 凭据、托管平面、真实 Provider/设备或审批缺失时必须失败且不得写 ready。
- 关联要求：`REQ-002`
- 影响 Story：[`reliability-policy-control`](./reliability-policy-control/spec.md) 的 hosted receipt 准出链路。
- 关联验收：`SIT-001`、`GWT-002`

<a id="dec-003"></a>
### DEC-003 镜像身份由部署包精确绑定且配置不声明兼容范围
- 决策：镜像内容以部署包内唯一的不可变 digest/ref 为事实；运行实例只回报该精确身份，服务 config schema 不再维护最低/最高镜像版本、兼容区间或环境例外。
- 理由：兼容范围无法证明当前实例实际运行的字节，且会把部署事实复制为第二套配置真相源；精确身份可直接关联 package、receipt、回滚目标和运行回读。
- 被否决方案：SemVer 上下界、多个可接受版本、空值视为本地开发、可变 tag、兼容解析或 fallback。
- 约束与影响：Kubernetes 包必须写入 digest annotation 并使用 `@sha256` 镜像引用；Compose 必须注入受门禁校验的精确 ref 和由其完整派生的单一摘要。标准 `apiVersion`、第三方包 SemVer 与镜像传输 tag 不作为服务兼容协议。
- 关联要求：`REQ-002`
- 影响 Story：[`config-source-governance`](./config-source-governance/spec.md)、[`reliability-policy-control`](./reliability-policy-control/spec.md)
- 关联验收：`SIT-001`、`GWT-001`、`GWT-002`

<a id="dec-004"></a>
### DEC-004 生产灰度按可信安装实例稳定分桶并单调扩张
- 决策：生产灰度只发生在 `prod` 环境内，由 `api-edge` 按可信 `deviceActorId` 裁决 stable/candidate 服务池；Android、iOS、Web 分别使用固定 context key 哈希和相同 basis-point 阈值抽样，百分比表示每个已选平台的合格去重安装实例比例，不表示请求量比例。
- 决策：活动内 `campaignId`、candidate digest、`allocationKeyId` 与 `subjectKind=device_actor` 不可变；阶段阈值只允许从 canary 依次扩大到 5%、20%、50%、100%，已建立的 candidate assignment 在同一活动中保持 candidate。平台、App Build、地域或运营商 audience 只能保持或扩大，任何收缩只能通过整个 campaign rollback 完成。
- 决策：地域和运营商默认全选并只作分层观测；定向时由可信代理源 IP 和固定摘要的 GeoIP/ASN 数据派生，命中后持久化 assignment，因此旅行、网络切换或归属变化不改变 cohort。`unknown` 是合法分层值，不能因不可识别而静默排除。
- 理由：稳定 subject 与单调阈值同时保证比例接近期望值、少数平台有样本、用户不在 stable/candidate 间漂移，并使阶段提升可回放和审计。
- 被否决方案：请求级随机、账号级分桶、让 Android 请求量吞并 iOS/Web 样本、由 App 自报可信地域/运营商、阶段间修改盐值或缩小过滤集合，以及把 Caddy 作为业务路由器。
- 约束与影响：assignment store 必须复制并持久化；不可用、数据丢失、candidate digest 漂移、默认平台缺样本或相邻阶段集合不满足包含关系属于 critical failure，campaign 自动进入 `rolled_back`，不得重新分桶或以内存状态继续。
- 关联要求：`REQ-002`
- 影响 Story：[`reliability-policy-control`](./reliability-policy-control/spec.md)
- 关联验收：`SIT-001`、`GWT-003`、`GWT-004`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 各服务自治维护 `sys.*` 配置来源，平台运维控制面统一发布、灰度、审计和回滚口径。
- 配置内容摘要、镜像精确身份与托管 receipt 分别证明其所属事实，并由同一候选发布关联；不得互相推断或复制兼容范围。
- 高风险配置和镜像发布必须可审计、可回读、可回滚；任一身份缺失或漂移均不得产生成功事实。
- 每阶段必须分别观测去重安装实例、去重账号和请求三个比例，并按 target、platform、App Version/Build、region、carrier 与 canonical operation 分层；过滤后的 eligible 占比与全体占比必须同时展示，不得用请求占比冒充安装实例占比。
