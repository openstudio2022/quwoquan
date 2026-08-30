# L3 Story：托管人类授权（Hosted Human Authority） (`hosted-human-authority`)

> 所属能力：[配置与可靠性治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为 Human-Agent 交付与 Objective 执行提供独立、可认证、可回读的 hosted authority
>
> 设计归属：[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为承担 Human Authority 职责的真实人员、受限自动执行方与发布运维方，我希望由独立 hosted provider 认证人员身份、封存决定、签发可精确验证且只能消费一次的授权，并在撤销、重放、断连、乱序、篡改或竞争时保持 fail-closed，从而不让 Portal session、GitHub job、Reviewer 结论、本地投影或测试 provider 冒充人类决定与生产授权。

## 2. 范围与非目标

### In Scope

- Hosted provider 的 Portal OIDC ingress、GitHub App webhook ingress 与 actor-to-role 映射接入。
- PostgreSQL append-only authority aggregate、原子 audit/outbox、provider signature、exact-byte readback、消费/撤销 CAS、storage 与 retention。
- Human-Agent canonical policy 对 `DecisionUnit`、两轮 sealed submission、eligibility 与 `DecisionRecord` 的持久化承载，以及 provider-owned `AuthorizationReceipt`。
- Objective consumer 对 exact bytes、expiry、EvidenceFingerprint、scope、decision/action 与 consume/revoke 状态的验证。
- 失败终态、恢复、回滚、authority wait/transfer/timeout 及 replay/conflict/consume/revoke 的观测与正式 hosted UAT 边界。

### Out of Scope

- `HumanAuthorityRole`、`DecisionKind`、DecisionUnit 职责和 SoD policy 的定义或闭集；这些只由 [`human-agent-delivery-interaction`](../../../runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md) 及其 canonical contract 拥有，Platform Ops 只按 exact contract/version 消费，不复制、不扩展、不兼容解析。
- Objective/Increment 状态、effect 两事件协议与 admission；这些只由 [`objective-execution`](../../../runtime/development-workflow-governance/objective-execution/spec.md) 及其 canonical contract 拥有。
- Portal 页面、业务 effect、GitHub 原生 branch/environment protection，或以 hosted authority 暗示原生 protection 已启用。
- 用本地 JSON/journal、projection、fixture、Reviewer PASS、Actions queue、Deployment status、人工布尔值或 test provider 生成正式 authority/release evidence。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 PostgreSQL append-only aggregate 与签名 exact-byte authority

- Hosted provider 必须以 PostgreSQL 中的单一 append-only aggregate 承载 canonical `DecisionUnit`、Round 1 `RoleSubmission` seal、Round 2 independent impact seal、`Eligibility`、`DecisionRecord`、provider-owned `AuthorizationReceipt` 以及 consume/revoke 事实；Human-owned 对象必须保存其 canonical contract/version 与 exact serialized bytes，不由 Platform Ops 重新定义字段、角色或决定种类。
- Round 1 封存前不得向提交者展示方案、其他角色偏好或 Agent 建议；Round 2 所有人消费同一冻结事实包与对称选项，各提交在汇总前彼此不可见。seal 一经提交只能追加 superseding round/decision，不得原地改写。
- 每个 aggregate event 必须带前序 digest 并进入可完整验证的 hash chain；`DecisionRecord` 和 `AuthorizationReceipt` 必须由 provider signing key 对 canonical exact bytes 与 chain position 签名。query 必须返回原始 exact bytes、摘要、签名、key id、chain proof 与 provider commit identity，不能重序列化后宣称等价。
- 形成决定或授权的事务必须把 decision event、audit event、outbox record 与 receipt bytes 原子提交；任一写入失败整体不提交。outbox 只投递已提交事实并按稳定 event identity 幂等，不能先发布后落库。
- consume 与 revoke 必须在同一 aggregate generation 上做 compare-and-swap 并追加事件。每份 executable receipt 恰好一个 consume winner；先线性化成功的 revoke 必须使后续 consume 与 effect 均不可执行。consume 已先线性化时，迟到 revoke 必须返回可区分冲突，不得改写历史或伪称已阻止既有 effect。
- expiry 只改变可执行资格，不删除历史。在线 storage、归档、签名公钥和 audit/outbox 证据必须遵循预冻结 retention 与 legal-hold policy；retention 结束前保持 exact-byte query，归档/清除只能走受审策略且不得删除仍有效、待消费、争议中或 legal-hold 的记录。

<a id="req-002"></a>
### REQ-002 Portal OIDC ingress 只接受 provider 验证的 principal 与角色映射

- Portal ingress 必须验证精确 issuer、audience/client、授权码回调、签名与 JWKS；`state` 与 `nonce` 必须一次性绑定原登录事务并防重放，适用的客户端必须使用 PKCE。JWKS 未知 key、issuer/audience 不匹配、state/nonce/PKCE 失败或 token 过期一律零 authority mutation。
- 本 Story 所有 Human Authority role-task/read/submit/authorize/recovery/audit route 只接受 verifier 签发的 `OperatorOIDC` principal；principal 必须保留 credential source、issuer、subject、mapped principal/roles、`acr`/`amr`、`auth_time`、MFA policy/version 与 `verified_at`，且这些事实不得由 client assertion。generic HS256 shared-secret bearer 不得进入该受信身份边界。
- actor identity、MFA/principal facts 只能来自已验签 token 与 provider readback；MFA 资格必须按预冻结 `acr`/`amr`、认证时间和 provider policy 判断，不能由请求参数或 Portal session 自报。
- actor-to-role 只能通过受控、版本化且可审计的 issuer/group/claim mapping 得到 canonical Human contract 已声明的角色；session、表单、URL、cookie 或 API body 不得自报、提升或覆盖 role。mapping 缺失、歧义、漂移或超出 canonical closed set 时保持 fail-closed。
- scope 必须同时受 OIDC client、principal mapping、Human policy 和目标 `DecisionUnit` 限制；重新认证、MFA freshness、角色转交与 session expiry 不得扩张已有 scope。

<a id="req-003"></a>
### REQ-003 GitHub App webhook ingress 验签、幂等且保持 request→approved 顺序

- GitHub ingress 必须从受控 GitHub App installation 接收官方 webhook，对原始 request bytes 校验 `X-Hub-Signature-256`，并在解析或 mutation 前完成常量时间验签；缺签名、签名错误或 secret 不可用全部拒绝。
- delivery ID 是 ingress 幂等键：同一 delivery ID 与同一 raw payload digest 的重放返回同一已提交结果且零新增 event；同一 delivery ID 携带不同 payload 必须作为冲突阻断、留审计且不得覆盖首份事实。
- event 与 action 只能来自 Platform Ops hosted provider canonical contract 声明的闭集；未知 event/action、缺必要官方事实或由调用方自造 reviewer decision 必须拒绝。该闭集不得从 workflow 名、job 状态或页面文案推断。
- 每个 accepted request/approved 事实必须精确绑定 installation、repository、workflow run/attempt、head SHA、candidate、environment 与 authenticated actor；approved 只有在同一 identity tuple 的 request 已提交后才能追加，乱序 approved 不得缓存为隐式批准。
- GitHub ingress 产生的 approval 仍须满足 Human canonical policy 的角色、scope、DecisionKind 与 SoD。GitHub actor、OIDC actor 或其他 provider identity 的关联必须显式、可审计且不可由 session 自报。
- GitHub approval 只作为 engineering/production approval 的 deep-link/transport：accepted fact 必须绑定 exact DecisionUnit/candidate/scope/role 与官方 approver principal，并进入同一 aggregate hash chain、audit/outbox transaction；`NativeProtection=false`，GitHub 事实本身不能独立形成 Human truth。

<a id="req-004"></a>
### REQ-004 高风险 SoD 不因团队规模降级

- Platform Ops 必须逐次消费 Human canonical contract 的 SoD 结果，不拥有或复制其 role、DecisionKind、风险分类或职责闭集。
- 当 Human policy 对某 `DecisionUnit` 要求 independent principals 时，适用职责必须由不同 authenticated principals 分别完成；同一 principal 的多角色记录、同一 session、共享账号、机器人代签或 Reviewer 身份均不能满足。
- 小团队、人员缺席、超时、值班压力或发布窗口都不能把 independent-principal-required 降为 role-record-only。真实 principal 不足时只能 transfer、hold、pause、escalate 或 abort，并保持零授权/零 effect。

<a id="req-005"></a>
### REQ-005 Objective consumer exact-byte 验证、单次消费与撤销先行

- Objective consumer 必须调用 hosted exact-byte query 并用受信 provider key 验证签名、hash chain、provider/contract version、expiry、EvidenceFingerprint、scope、DecisionKind 与 action；消费规则引用 Human 与 Objective canonical contracts，不在 Platform Ops 创建影子闭集。
- query/readback absent、failed、断连、过期、fingerprint/scope/decision/action 不匹配、签名或 chain 无效、bytes 被重序列化、receipt 已撤销/消费，全部必须在 journal mutation 与外部 effect 前 fail-closed。
- consumer 只有取得同一 receipt 的 consume CAS winner 与签名 consume readback 后才能进入 Objective-owned effect 协议；竞争 loser 必须重新 readback 且零 journal mutation、零 effect。revoke 已先成功时，consumer 即使持有旧 receipt bytes 也不得执行。
- 乱序、重复 delivery、重复 command、网络超时或 result unknown 不得触发猜测性重试。authority 结果未知时只允许 readback/reconcile；不得签发第二 receipt、第二 consume 或第二 effect。

<a id="req-006"></a>
### REQ-006 Command/query/event、错误终态与恢复单轨

- Provider contract 已由独立 authoring source 冻结 command/query 边界、GitHub ingress、错误终态、storage 与 projection；具体 operation、字段、错误码、route 和 wire schema 只属于该 canonical contract，本 Story 不创建第二份 wire 真相源。Go provider、PostgreSQL aggregate 与 Objective hosted adapter 只能消费该 authoring source 及其生成绑定，不得从 spec 或本地 fixture 派生第二套协议。
- 所有 command 必须返回 committed、duplicate、conflict 或 blocked 等可区分终态；query 必须区分 present、absent 与 failed。authentication、mapping、SoD、顺序、CAS、expiry、signature/chain、storage、outbox 或 provider availability 失败不得折叠为 absent 或成功。
- role submission、request-evidence、transfer、pause/hold/abort 与 independent post-check/result-acceptance 必须是可独立执行和 readback 的 append-only command，post-check 不得再次 seal/finalize。role-record-only 的同一 principal 多角色记录必须可逐条接受，generic writer 不得 seal。last valid submission 的 server-side atomic auto-seal 是正常路径，独立 `seal-orchestrate` capability 只用于受权恢复。
- Provider 必须以 role-task query 给 Portal 投影恰好一个 pending capability 与 canonical 四类卡；旧/未知 schema、raw aggregate fallback、`intake` shadow card、handwritten recommendation gate 和 Portal 自造 permission namespace 均 fail-closed。raw audit/evidence 只能经 least-privilege audit query/scope。
- 每个 mutation 的 idempotency reservation、request digest、aggregate event/hash chain、audit、outbox、projection/receipt 与 committed exact response 必须处于一个 PostgreSQL transaction；多实例竞争由数据库唯一约束/CAS 裁决，相同请求重试 byte-identical，不依赖进程 mutex。
- HardVetoOwner 必须通过 formal role task 提交 option-specific pass/fail；ordinary role、creator 或 AccountableDecider 不得代填，missing/fail 阻断 eligibility/seal/finalize 并产生 typed readback。
- 恢复规则：duplicate 通过 exact readback 返回原结果，CAS/consume/revoke conflict 先 readback 后由新 expected generation 重试合法动作，outbox 失败从原子提交的未投递记录重放。unknown ingress/consumer outcome 只 readback/reconcile。身份、签名、tamper、scope、expiry、SoD 与 policy 错误只能重新认证、修复配置、补齐正确 principal/证据或形成新决定，不能 fallback。
- 单轨 cutover 后旧 unsafe/unversioned projection 与 mutation schema 必须 fail-closed；不得长期 dual-read/dual-write。部署 rollback 只能回到仍消费新 schema 的版本，否则停止 mutation并保留 query/audit/revoke，不能重新接受旧 mutation wire。

<a id="req-007"></a>
### REQ-007 正式证据必须来自 live hosted provider

- 本地 test provider、fixture、projection、本地 authority JSON、Objective local journal 和 mock OIDC/GitHub payload 只允许绑定本地契约验证或受限接口集成验证，必须显式标记 non-release-evidence，永不关闭 live identity、durability、signature、consume/revoke 或 release readiness。
- 正式用户验收必须使用：受控 GitHub App installation 与 webhook secret、真实 hosted PostgreSQL、独立 provider signing key、正式 OIDC issuer/client/JWKS/groups，以及至少两个不同的真实 MFA principals。若 Human policy 对目标决定要求更多独立 principals，该要求继续成立，两个不是降级上限。
- 正式用户验收必须以同一 immutable candidate 覆盖 Portal 与 GitHub 两个 ingress、两轮 seal、签发与 exact-byte readback、Objective consume、revoke-before-effect，以及断连、乱序、重放、篡改、过期和并发竞争负例；readback 还必须明确 hosted authority 不等于 GitHub 原生 protection。
- Provider contract、本地 Go/PostgreSQL 实现与 Objective hosted adapter 的 PASS 只关闭本地实现证据；在 hosted infrastructure 与上述外部前置全部闭合前，任何 local PASS、spec freeze 或 projection 都不得声明 authority ready、release ready 或 production ready。

## 4. 契约引用

- Human Authority policy owner：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`；本 Story 只消费其 exact version/digest、对象 bytes 与闭集裁决，不复制 role、DecisionKind 或 SoD。
- Objective consumer owner：`quwoquan_ops/policies/objective_execution_contract.yaml`；本 Story提供 authenticated exact-byte authority port，不拥有 Objective state/effect 协议。
- Platform Ops hosted provider contract：`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/human_authority/operations.yaml` 及同对象 authoring sources；Go provider、PostgreSQL storage、Portal client 与 Objective hosted adapter 均按该 contract/version 消费，contract 的 commercial 状态在 `OPEN-002` 闭合前保持 blocked。
- 生产 approval consumer：[`gray-release-to-prod`](../../../runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 append-only aggregate 原子提交、exact bytes 与竞争收敛

- GIVEN 一个绑定 canonical Human contract version 的 DecisionUnit，两个 round submission 已按适用职责与 SoD 准备，且 hosted PostgreSQL 与 signing key 可用。
- WHEN 两轮依次 seal、计算 eligibility、记录决定并签发 receipt，同时注入 transaction/outbox 失败、同 generation consume/revoke 竞争与重复 command。
- THEN decision、audit、outbox 与 receipt 要么原子提交并可 exact-byte query、验签和验证完整 hash chain，要么全部不提交。
- AND duplicate 只返回同一 exact result，stale CAS 零新增 event；每份 receipt 只有一个 consume winner，先提交 revoke 时所有 consume/effect 均被阻断。
- AND retention 前 exact bytes 与 chain proof 始终可读，expiry 不删除审计历史。

<a id="gwt-002"></a>
### GWT-002 OIDC 身份、MFA、mapping 与 scope fail-closed

- GIVEN Portal 连接正式配置的 OIDC issuer/client/JWKS/group mapping，目标决定要求 authenticated principal 与适用 SoD。
- WHEN 真实人员完成登录、MFA 和角色职责内提交，或请求包含错误 issuer/audience/key、重放 nonce/state、失败 PKCE、自报 role、过期认证、mapping 歧义与 scope 越界。
- THEN 只有已验签、满足 MFA freshness 且由受控 mapping 得到 canonical role 的 principal 能在限界 scope 内追加 submission。
- AND 所有负例零 authority mutation、零 receipt、零 effect；session 自报 role 和同 principal 绕过 independent-principal-required 均被阻断。

<a id="gwt-003"></a>
### GWT-003 GitHub webhook 验签、delivery 幂等与顺序闭合

- GIVEN 受控 GitHub App 已安装并为同一 repository/run/head/candidate/environment 产生官方 request 与 approved 事件。
- WHEN ingress 接收合法顺序事件，以及签名错误、未知 event/action、同 delivery 同 payload 重放、同 delivery 不同 payload、approved 先到、identity tuple 漂移等负例。
- THEN 合法 request→approved 各只追加一次并绑定完整官方 identity；同 payload 重放返回原结果，不同 payload 冲突、乱序与漂移均 fail-closed。
- AND exact-byte readback 明确声明 hosted external authority，不把 workflow queue、Deployment status 或原生 protection 当审批事实。

<a id="gwt-004"></a>
### GWT-004 Objective exact-byte consume/revoke 在故障与竞争下零越权 effect

- GIVEN Objective consumer 收到一份 hosted receipt reference 与预期 fingerprint、scope、DecisionKind、action，并有受限 effect adapter。
- WHEN 发生正常 consume、两个 consumer 竞争、revoke 先提交、断连、乱序、重放、receipt/chain 篡改、expiry 或任一预期 claim 漂移。
- THEN 只有 exact bytes 验签和全部预期成立后的单一 consume winner 能交给 Objective-owned effect 协议；loser 与全部负例零 journal mutation、零 effect。
- AND unknown 只进入 readback/reconcile，不能重试性签发、consume 或执行；revoke-before-effect 可由 authority 与 effect readback 共同证明。

<a id="gwt-005"></a>
### GWT-005 live UAT 与本地证据资格严格分离

- GIVEN local test provider 已通过结构测试，但正式 GitHub App/secret、hosted DB、signing key、OIDC 配置或两个真实 MFA principals 任一缺失。
- WHEN 准出方评估 hosted Human Authority readiness。
- THEN local/projection 证据保持 non-release-evidence，readiness 为 blocked，不能声明 authority ready。
- AND 只有全部正式前置就绪，并由至少两个不同真实 MFA principals 在同一候选完成 GWT-002 至 GWT-004 的正负 live UAT，才可提交 release evidence；更严格的 Human SoD 仍须完整满足。

## 6. 依赖

- 前置要求：Human 与 Objective canonical contracts 保持单点 owner，hosted provider 只消费 exact version/digest。
- 上游事实：已认证 principal/role、canonical DecisionUnit bytes、Objective expected fingerprint/scope/decision/action。
- 下游结果：签名 exact-byte authority readback、单次 consume/revoke 终态与原子 audit/outbox 事实。
- 父级设计：`DEC-005`。
- 运行约束：Command/query 物理分离；ingress 不直接执行 Objective effect，consumer 不直写 authority storage。
- rollback 不删除或重写 authority history：provider 版本回滚必须保持旧 schema/readback 与历史 signing key 可验证，停止新签发时仍允许只读验证与安全 revoke；业务 effect 的补偿或回滚必须取得新的有效 Human decision。
- 单轨 cutover 后不得 dual-write/dual-read 本地 provider 与 hosted provider，也不得把旧 projection 作为 fallback。
- 可用性 SLO（按月）：authenticated command 与 exact-byte query 服务可用性不低于 `99.9%`；provider 自身写入 p95 不高于 `2s`、exact-byte query p95 不高于 `1s`，均排除真实人类等待时间。
- durability/propagation SLO：webhook 在 durable atomic commit 后响应，commit p95 不高于 `2s`；已提交 outbox 的 `99.9%` 在 `60s` 内投递，连续 `5m` 未前进告警。任何超标不得把未提交或未投递事实伪装为 approved/consumed。
- 安全 SLO：被接受的无效签名、tamper、过期授权、重复不同 payload、SoD 绕过、多 consume winner、revoke 先行后的 effect 均为 `0`；出现一例立即 P0 告警并停止新签发/消费，保留 exact readback 与 revoke 能力。
- Authority wait/transfer/timeout 按 delivery stage、DecisionKind、required role、provider 与 terminal 观测等待时长、转交次数和超时数；人类等待不计入 provider latency，但 `100%` timeout 必须产生 canonical fail-closed terminal，不能隐式批准。
- replay/conflict/consume/revoke 必须分别记录计数、延迟、winner/loser、recovery 与 correlation identity；日志和指标不得暴露 token、webhook secret、raw PII 或 signing private key。
- partial commit、outcome unknown、stale task、wrong role、scope denied、hard veto missing/failed、auth freshness、GitHub mapping/SoD、idempotency replay/conflict 与 projection/schema mismatch 必须分别保留 typed terminal、恢复动作、计数、延迟和 reconciliation age；不得折叠成 generic absent/error。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Provider role-task/recovery/identity contract 待无冲突单轨落地

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：provider-owned RoleTask/CardProjection、独立 recovery/post-check commands、server atomic auto-seal、formal HardVetoOwner result、transactional committed response、OperatorOIDC principal、GitHub principal/role/SoD binding、generated operation capabilities、typed terminals 与 single-track cutover 尚未落入 Human contract、hosted provider authoring contracts、control-plane operation refs 及其生成绑定；在这些路径的并行写入结束前，本 OPEN 不竞争其字节。尚缺验收证据：对应 local_contract/api_integration 尚未证明旧 raw aggregate/HS256/generic seal/compound Portal mutation 已被单轨拒绝。
- 完成判定：`GWT-001.t1`、`GWT-001.t2`、`GWT-002.t1`、`GWT-002.t2`、`GWT-003.t1`、`GWT-004.t1`、`GWT-004.t2` 由同一单轨 authoring contract 及 local_contract/api_integration 直接绑定，且旧 projection/mutation fail-closed、无 dual-read/write/fallback。
- 依赖：占用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml`、`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/human_authority/**`、control-plane operation refs 与 Objective exact-byte/consume wire 的并行 writer 完成后，按 authoring source → verify/codegen → implementation/tests 顺序落地；Objective operations/model/facade exact-byte/consume bytes 保持由其 owner 独立修改。

<a id="open-002"></a>
### OPEN-002 正式 hosted identity、infrastructure 与 live UAT 前置未满足

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺受控 GitHub App installation/webhook secret、真实 hosted PostgreSQL、独立 provider signing key、正式 OIDC issuer/client/JWKS/groups 与至少两个不同真实 MFA principals 的正式 hosted UAT evidence；本地 test provider 与 projection 永不关闭此边界。
- 完成判定：`GWT-005` user_acceptance 在同一 immutable candidate 上完成，并覆盖 `GWT-002`、`GWT-003`、`GWT-004` 的正负例；证据明确区分 hosted external authority 与 GitHub native protection，且满足 Human policy 要求的全部 distinct principals。
- 依赖：GitHub 管理员安装与 secret、托管数据库/备份/retention、KMS/HSM 或等价 signing key 管理、OIDC 管理员配置、真实 MFA 参与者、prod-hosted 网络与观测通道。
