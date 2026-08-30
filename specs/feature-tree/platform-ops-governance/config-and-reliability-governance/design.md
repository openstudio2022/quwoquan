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

<a id="dec-005"></a>
### DEC-005 Hosted Human Authority 采用 provider-owned role task、原子 PostgreSQL command receipt 与受验证双 ingress
- 所有权：Human Authority 的 role、DecisionKind、DecisionUnit 七责、SoD、四类卡与推荐禁区继续由 runtime `human-agent-delivery-interaction` 及 `human_agent_delivery_contract.yaml` 单点拥有。Platform Ops provider 只拥有 authenticated principal/role mapping、`RoleTask/CardProjection` wire、provider capability、append-only persistence、签名/readback、consume/revoke、audit/outbox/retention；不得重定义 Human 闭集或把 Portal/GitHub/Reviewer 状态提升为 Human truth。
- Query/审计隔离：authenticated role-task query 只返回与 `DecisionUnit/candidate/scope`、mapped principal、恰好一个 pending role/task capability 绑定的 canonical 四类卡投影，包含 stage/state、allowed operations、安全默认、pending roles、expiry/freshness、recommendation visibility、recovery state 与脱敏 role projection。raw aggregate、RoleSubmission evidence、audit、exact bytes 与 chain proof 走独立 least-privilege audit query/scope；角色主 query 不返回 raw fallback material。未知/旧/未版本化 projection 必须 typed fail-closed。
- 命令与事件：role submission、request-evidence、transfer、pause/hold/abort 与独立 post-check/result-acceptance 均为 append-only command/event/projection，绑定 current task capability、actor role、scope、expected aggregate generation、idempotency key/request digest。request-evidence 只使任务等待新 evidence，transfer 只重分配 canonical 合法角色且不扩大 scope，pause/hold/abort 只进入安全终态。post-check 只追加所属 ResultAcceptor 的 acceptance，不得 seal 或 finalize 同一 DecisionUnit。每条 command 返回 accepted/pending/next-role 或相应 recovery state，readback 可独立重建。
- 多角色：`role-record-only` 允许同一 principal 依序取得不同 role task capability 并形成独立 role records，`independent-principal-required` 对适用职责验证 distinct actors。
- seal：provider 在最后一份有效 submission 的同一事务内自动 seal round，或只向独立受权 orchestrator 签发 `seal-orchestrate` capability；首选并冻结前者，后者仅用于显式恢复。generic write scope、DecisionUnit creator、普通 role 与 Portal 都不能 seal。submission 已提交但 seal 结果 unknown 时只 query/reconcile，不撤销已接受 submission、不盲重交。
- Hard veto：HardVetoOwner 对每个适用 option 通过正式 role task 提交 option-specific `pass|fail` result，并绑定 gate/evidence/freshness。普通 role、creator、AccountableDecider 与 orchestrator 均不能代填。required veto 缺失、过期或 fail 使 option 不可 eligible，阻断 seal/finalize 并通过 typed readback 返回 failed/missing gate 与合法恢复。多数票、风险接受、recommendation 或 generic scope 不能覆盖。
- 原子幂等：每个 provider command 先以 `(operation, idempotency_key)` reservation 绑定 canonical request digest，并在同一 PostgreSQL 事务提交 aggregate event/hash-chain、audit、outbox、projection、receipt 与最终 status/headers/exact response bytes。reservation 不能脱离 mutation 单独成功。多实例以 database unique/CAS/row lock 串行化，相同 digest 重试 byte-identical readback，不同 digest conflict。正确性不依赖进程 mutex、实例 sticky routing 或 Portal 合成响应。
- Principal 与 OIDC：`AuthenticatedPrincipal` 只能由 verifier 构造，携带不可由 client assertion 的 credential source=`OperatorOIDC`、issuer、subject、mapped principal/roles、acr/amr、auth_time、MFA policy/version、verified_at。Human Authority role-task/read/submit/authorize/recovery/audit route 均要求 OperatorOIDC，并按 route/provider policy 校验 max authentication age、MFA 与映射版本。Portal OIDC state/nonce 一次性绑定登录事务并支持 freshness re-auth。无凭据或失效 token 为 401，已认证但 scope denied 或 wrong role 为各自 403。body/header/session 不能覆盖 principal facts，generic HS256 shared-secret bearer 不在受信 ingress 集合内。
- GitHub ingress：只接受受控 GitHub App 的官方 actor/approver/request/review facts，raw payload HMAC 验证先于 parse/mutation，delivery id + raw digest 幂等。audited mapping 将 installation/repository/actor 映射到 provider principal/role，并精确绑定 DecisionUnit/candidate/scope/task role、PR/head SHA/run-attempt 与 SoD。mapping missing/ambiguous/drift、self-approval、wrong role/scope、approved-before-request 均零 authority mutation。accepted fact 与 aggregate event、hash chain、audit/outbox、exact committed response 在同一事务。`NativeProtection=false` 固定，GitHub 只是 engineering/production approval deep-link/transport，不能独立成为 Human truth。
- Recommendation 与 capabilities：provider 只在 required rounds sealed 后投影 recommendation，并强制 assumptions/counterexamples/alternatives，canonical forbidden decision kinds 永不投影。operation capability 闭集由 provider authoring contract 生成并由 Portal 消费，至少区分 role-task read、role submit、seal-orchestrate、authorize/finalize、recovery 与 audit。permission namespace 不由 Portal 手写。
- 单轨迁移：部署采用 versioned projection/capability 的单轨 cutover，不长期 dual-read/dual-write、不保留 raw aggregate 或旧 mutation fallback。cutover 前停止旧 mutation、完成 pending idempotency/outcome reconciliation、部署 provider 后再部署只认新 schema 的 Portal，旧 unsafe/unversioned projection fail-closed。
- 回滚：部署 rollback 只能回到仍理解新 mutation schema/committed response 的 provider/Portal。若无兼容版本则停止 mutation、保留新 query/audit/revoke，不重新接受旧 schema。历史 append-only bytes/key/version 保持可验证。
- 失败恢复：duplicate 读回 exact response。request digest conflict 由调用者更换 key 或修正原请求。CAS/stale task 重新 query capability。partial response/outcome unknown 按 operation+key reconcile committed response。outbox 从事务内记录幂等重放，auth freshness 重新认证，wrong role/scope 转交或修复 mapping，hard veto 只补齐或更新 owner evidence 或形成新合法决定，projection mismatch 停止 mutation 并部署匹配版本。任何恢复都不扩大 scope、不重写 history、不猜测 success。
- SLI/SLO/typed terminals：月度 authenticated command/role-task query availability `>=99.9%`，provider write p95 `<=2s`、query p95 `<=1s`，outbox `99.9% <=60s` 且 `5m` 无进展告警。分别观测 `partial_commit|outcome_unknown|stale_task|wrong_role|scope_denied|hard_veto_missing|hard_veto_failed|auth_freshness|github_mapping|github_sod|idempotency_replay|idempotency_conflict|projection_schema_mismatch` 的 count/latency/reconciliation age 与 correlation identity；不使用 actor/PII label。partial commit、无效 auth 接受、SoD 绕过、多 winner、旧 projection fallback 与 veto 绕过预算均为 0，一例 P0 并停止新签发/消费，保留 query/audit/revoke。
- 测试 seam：`local_contract` 锁定 projection/card/capability 闭集、principal verifier source、401/403、veto ownership、recommendation gate 与 zero fallback。`api_integration` 在至少两个 provider instance 上以真实 PostgreSQL 锁定 reservation+mutation+audit+outbox+exact response 单事务、same-key same/different digest、crash-after-each-write、automatic seal、recovery events、OIDC verifier policy 与 GitHub mapping/SoD/hash-chain，contract golden 锁定 byte-identical retry。`user_acceptance` 才能用正式 OIDC/GitHub/PostgreSQL/KMS/MFA principals 与真实 screen-reader 关闭 external OPEN，本地证据不得升级。
- 理由：role task、Human policy、hosted identity、aggregate transaction、GitHub transport 和 Objective execution 是不同事实边界。provider-owned projection、database-linearized committed response、verifier-issued principal 与 option-specific veto 能在多实例、崩溃、网络未知和多角色条件下恢复，同时阻止 Portal 或 generic writer 自我授权。
- 被否决方案：否决 Portal raw aggregate 解释/fallback、通用 HS256、client role/MFA assertions、in-process mutex 正确性、幂等 response 与 aggregate 分事务、generic writer seal、submit+seal 复合 API、post-check finalize、creator/普通角色 veto、GitHub approval 自成 Human truth、handwritten recommendation gate、permission namespace 双轨、长期 dual-read/write 和删除历史式 rollback。
- 适用工程根：`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/human_authority`、`quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority`、`quwoquan_service/control-plane/platform-ops/tests/local_contract/platform_ops/human_authority`、`quwoquan_service/control-plane/platform-ops/tests/api_integration/platform_ops/human_authority`、`quwoquan_ops/cli/hosted_authority.py`、`quwoquan_ops/cli/hosted_authority_smoke.py`、`quwoquan_ops/cli/lib/hosted_authority`、`quwoquan_ops/cli/lib/objective_execution/hosted_provider.py`、`quwoquan_ops/tests/local_contract/gate/test_hosted_authority_adapter__local_contract_test.py`
- 关联要求：`REQ-003`；L3 [`hosted-human-authority/REQ-001`](./hosted-human-authority/spec.md#req-001) 至 [`REQ-007`](./hosted-human-authority/spec.md#req-007)。
- 影响 Story：[`hosted-human-authority`](./hosted-human-authority/spec.md)。
- 关联验收：`GWT-001` 至 `GWT-005`。

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
