# L3 Story：灰度发布到生产 (`gray-release-to-prod`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “灰度发布到生产”的输入、可观察主路径、失败语义以及与父能力的交接。
- prod `canary` 的 hosted deploy、只读/幂等 api_integration 与 Journey/Page user_acceptance。
- rollout stage 配置、SLO 决策、审批与回滚证据。
- 与 local-gamma-mirror 的职责边界收敛。
- 提交前本地左移链路。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。
- 新增生产环境枚举、`prod-gray` 第二环境或第二套发布拓扑。
- 已退役的 Kubernetes/`PROD_KUBECONFIG` 执行面。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 唯一生产 effect 入口

- workflow、Portal 与人工命令只能提交 stable `ReleaseTagAdmissionFact` exact ref，并最终收敛到 `stackctl deploy --target prod-hosted ...`；不接受 main HEAD、裸 SHA、RC tag、mutable OCI tag、repository variable 或 latest-qualified 查询。

<a id="req-002"></a>
### REQ-002 activation 物料物化与 mutation 前阻断

- rollout 只消费 `ProdActivationAdmissionFact` 物化并绑定的 `CandidateMaterialManifest`、`service_factory_material`、`app_factory_material` 与 factory OCI exact bytes；workflow scalar 不得替代实际 payload readback。
- 在任何 production mutation 发生前，pre-mutation gate 必须复验 factory payload、`materialDigest`、source、tree、request、RC、signature、attestation 与 config/deployment bundle 闭包；任一不一致返回 `GATE_BLOCK`，不得进入 activation、stage、rollback 或 terminal 写入。
- CLI 必须明确拒绝 `stackctl package --kind release-manifest` 和 formal `--release-manifest`；formal rollout 不接受 `prevalidate` / `prod-sim` 历史 snapshot。

<a id="req-003"></a>
### REQ-003 stable tag 绑定的 Prod 单事务终态链

- 系统只有一个 `prod` 环境；`canary / 5 / 20 / 50 / 100` 只是同一 `prod-hosted` 的 rollout stage，`prevalidate` 不是正式 stage。production approval 后只验签、解包和物化一次，随后由 `stackctl` 在同一事务依次推进五个 stage，后四阶段 builder invocation 必须为零。
- 每次 stage 只追加 `ProdStageAttemptFact` 及其 activation、health、SLO、placement、readback 前驱；失败 retry 追加新 attempt。stage `100` 成功后 create-once 生成 `ProdReleasedFact`，不得以 lifecycle status transition 替代终态事实。
- rollback 只引用 admission 已绑定的 exact previous `ProdReleasedFact` 与 rollback readiness，不得移动 tag、重建旧 commit 或猜测版本；`PostReleaseSoakFact` 只读 exact current `ProdReleasedFact`，且不改变 tag、QualificationFact、Prod terminal 或 release identity。

<a id="req-004"></a>
### REQ-004 云上 prod-sim 内部验证环

- `prod-sim` 是 `prod-hosted` 执行面内的 validation ring，唯一 deployment instance 映射为 `prevalidate`，不是第五环境或正式 rollout stage；本地模拟结果不能作为云上准出。
- 生产 App 保持 prod canonical URL。现有 rollout assignment policy 唯一拥有验证环访问条件：精确 platform/displayVersion/buildNumber 到已验真 App artifact digest 的映射、candidate digest、目标 instance、用户白名单与可信 IP/CIDR。RC 标签沿用 `vMAJOR.MINOR.PATCH-rc.N`；iOS displayVersion 使用不含标签前缀/RC 后缀的三段版本号，以单调 buildNumber 区别内部构建。
- 用户与 IP 白名单均可独立配置：已配置的账号/设备名单内部 OR；只配置用户则只限制用户，只配置 IP 则只限制 IP，两类同时配置则 AND，再与精确版本条件 AND。省略的列表不施加该类限制；显式空列表拒绝该类所有主体，不得按省略处理；两类均省略时验证环默认拒绝。部署 `requireIp=true` 是额外限制：未配置 IP 列表或缺失可信 IP 时拒绝，`requireIp=false` 才允许 user-only。非法 CIDR、candidate/target/upstream/policy digest 漂移均拒绝；客户端身份/IP/region/carrier/artifact 摘要不成为信任来源。
- 验证环占用的 candidate 池与正式百分比 rollout 互斥；每个请求重新判断全部条件，不读写正式 campaign sticky assignment，也不借用 internal canary 的 OR 放行。配置移除或名单撤销后，既有 assignment 不得绕过新条件。
- 验证环只消费 main/RC/CMM/Qualification 对应 prod trust-domain exact artifacts，不重新构建或签名。hosted inventory、运行身份与 route readback 必须证明 target、instance、candidate、upstreams、配置和数据绑定一致；无法证明时保持禁用。
- 复用现有 hosted deployment/prevalidate receipt，记录 exact authority refs、policy digest、readback、真实 Provider/内容/媒体/iOS 真机 Journey 和 cleanup 结果；`publicExposure=false`、non-promotable，不签发新发布 Fact，不写正式 activation/released authority。

## 4. 契约引用

- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 stable tag绑定的灰度发布

- GIVEN 一个不可移动 stable `ReleaseTagAdmissionFact` 绑定 main-reachable commit、qualified RC、exact previous `ProdReleasedFact` / rollback readiness 与有效 production approval。
- WHEN 受保护 runner 执行正式发布。
- THEN `ProdActivationAdmissionFact` 只物化并复验一次实际 `CandidateMaterialManifest` 与两个 factory material OCI canonical bytes，随后经 `stackctl` 完成 `canary -> 5 -> 20 -> 50 -> 100`；每阶段追加 `ProdStageAttemptFact` 与签名 revision、目标实例 ACK、health/SLO/readback，stage `100` create-once 生成 `ProdReleasedFact`，且 builder invocation 为零。
- AND 任一 factory payload、materialDigest、source、tree、request、RC、signature、attestation、config/deployment bundle 或后继 exact ref 漂移均在 mutation 前 `GATE_BLOCK`，workflow scalar、tag 移动或 latest 查询均不能绕过。
- AND 阶段失败只按 exact previous `ProdReleasedFact` / rollback readiness 回滚，soak 只引用 exact current `ProdReleasedFact`；CLI 拒绝 `package --kind release-manifest` 与 formal `--release-manifest`，formal 不接受历史 snapshot，且不存在 `ReleaseEvidenceManifest`、`releaseEvidenceRef`、public release-manifest writer、lifecycle status transition 或第二 effect 入口。

<a id="gwt-002"></a>
### GWT-002 云上 prod-sim 验证环隔离与非提升性证据

- GIVEN 同一 main/RC/CMM/Qualification 绑定的 exact 制品、可信身份/IP 和精确 App 版本映射，部署实例为 `prod-hosted/prevalidate`，且不占用正式百分比 rollout 的 candidate 池。
- WHEN 内部用户通过 prod canonical URL 访问验证环，并逐项撤销版本、用户、可信 IP 或 candidate route 绑定条件。
- THEN 仅满足精确版本及全部已配置白名单限制的请求进入 exact candidate：user-only、IP-only 各自生效，both 为 AND，none 默认拒绝；显式空列表、已配置条件不匹配、部署 requireIp 未满足或摘要漂移均拒绝，旧 sticky assignment 不得绕过重新判断。
- AND hosted readback 证明 instance、candidate、upstreams、配置与隔离数据一致；真实 Provider、内容/媒体、签名 iOS 真机 Journey 和 cleanup 的结果绑定同一 candidate，缺少任一 required 证据保持 `GATE_BLOCK`。
- AND receipt 必须声明 `publicExposure=false` 与 non-promotable，不写正式 activation/released authority，也不把本地 contract PASS 或历史 snapshot 当作 hosted 验收通过。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 prod canary 承接真实远端复验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：生产灰度口径已统一为 prod rollout stage，但仍缺真实 canary 对 activation 物化 factory exact bytes、mutation 前篡改阻断与 create-once terminal 的直接证据。
- 完成判定：`GWT-001` 的物料物化、stage attempt、stage `100` terminal 与 mutation-before-block 结果在真实 prod canary 承接中满足，且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 prod canary 到 100 与自动回滚真实演练

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：CI 与 stackctl 接线不能替代真实 ssh-hosted 灰度、SLO gate 和回滚证据。
- 完成判定：`GWT-001` 对应行为满足。通过 `stackctl deploy --target prod-hosted`，使用按 `edge / media / service / data` 平面隔离的 `PROD_*_SSH_KEY` 与发布 secrets，完成 `canary -> 5 -> 20 -> 50 -> 100`、故障注入、SLO 阻断和自动回滚，且全部证据绑定同一 candidate digest。
- 依赖：生产托管主机账号、各平面 SSH 凭据、渠道/数据面 secrets 与发布审批。

<a id="open-004"></a>
### OPEN-004 production approval durable review event

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：GitHub Deployment、Deployment Status 与 Actions review-history 的当前只读响应没有同时给出 required-reviewer 请求和批准的明确事件时间；私有仓当前套餐也无法启用原生 required reviewers。用 `queued/in_progress` 或 Prod job `started_at` 替代会把 runner/concurrency queue 误算成审批，造成 timing 假绿。
- 完成判定：`GWT-001` 的“只申请一次 production approval”分项由受控 GitHub App/webhook 与 hosted authority 直接覆盖——webhook 验签后 append-only 持久化 request/approved 事件及接收时间，严格绑定 delivery ID、installation、repository、workflow run、head SHA、candidate、environment 与 reviewer decision；workflow exact-byte 回读生成 approvalRequestedAt、approvalApprovedAt、humanDecisionWait 与 approvalWait，且回执声明 `nativeProtection=false`、`enforcement=external_hosted_ledger`，不再存在对应 `missingEvidence`。
- 依赖：GitHub 官方可订阅事件、GitHub App installation/webhook secret、受控接收面与 hosted approval authority 不可变回读。

<a id="open-006"></a>
### OPEN-006 云上 prod-sim validation ring 尚无当前真实准出

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`prod-hosted/prevalidate` 的访问裁决具备本地 contract，但运行配置加载器尚未消费受管 hosted route/readback 前驱，必须拒绝启用 validation ring；自报 candidate/artifact/runtimeConfig 摘要不能替代验真。仍缺同一 RC/CMM/Qualification exact bytes、真实 Provider、隔离数据、签名 iOS 真机、route readback 和 cleanup 的 hosted receipt。
- 完成判定：`GWT-002` 全部结果子句均由同一 candidate 的 hosted non-promotable receipt 直接证明；缺失云主机凭据、Provider、设备或发布授权时保留首个 typed blocker。

<a id="open-005"></a>
### OPEN-005 动态灰度激活迁移到 Platform Ops hosted authority

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `quwoquan_ops/environments/prod/rollout/routing_policy.yaml` 仍把动态 `campaignId/candidateDigest/stage/status` 保存在 IaC 发布包内，每次放量推进都要走一次发布包变更；Portal 只读，无受控激活入口。DEC-007 已冻结边界：灰度激活是 Platform Ops 拥有的流量策略，stage 不改变制品、配置包与候选身份（候选摘要结构性排除激活事实已有 local_contract 证据）。
- 完成判定：本 Story `GWT-001` 与 [`reliability-policy-control` 的 hosted rollout activation authority 验收](../../../platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-005) 对应行为满足。IaC 仅保留策略 schema、合法阶段与静态约束，动态字段迁到 Platform Ops hosted activation authority。Portal 只提交强类型激活意图，`api-edge` 读取签名 active revision 并原子切换，`stackctl` 保持唯一 effect 执行与灰度激活回执入口。单轨 cutover 在同一受审增量内删除 IaC 动态字段读取（含 `deploy_rollout`、promotion evidence、`verify_gray_routing_policy` 与 api-edge runtime config 的 reader 同步），不保留 dual-read。
- 依赖：[`reliability-policy-control OPEN-002`](../../../platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#open-002) 交付 Platform Ops rollout activation aggregate 与公开契约；api-edge 签名 revision 读取通道和 prod plane 部署链同步消费。

<a id="open-002"></a>
### OPEN-002 灰度发布到生产 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺能够证明当前 GWT 全部结果子句的职责匹配证据，尤其是 release-manifest CLI 拒绝、formal snapshot 拒绝与 terminal predecessor 单轨。
- 完成判定：`GWT-001` 全部结果子句分别由 current local_contract/api_integration/user_acceptance 直接绑定并通过；真实 hosted rollout 仍以 `OPEN-003` 的外部证据关闭。
