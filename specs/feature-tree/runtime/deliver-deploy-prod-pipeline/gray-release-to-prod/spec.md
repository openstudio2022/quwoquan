# L3 Story：灰度发布到生产 (`gray-release-to-prod`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

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
### REQ-001 灰度发布到生产

- **统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。

<a id="req-002"></a>
### REQ-002 统一入口：workflow 与人工命令最终都收敛到 stackctl deploy --target prod-hosted ...

- **统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`

<a id="req-003"></a>
### REQ-003 prod 单环境分阶段放量

- 系统必须只有一个 `prod` 生产环境。`canary / 5 / 20 / 50 / 100` 只是同一 `prod-hosted` 目标的 rollout stage；`prevalidate` 只做不可提升的容器预验证，不属于 rollout stage。
- 多主机 / 多 replica 仍是一次 `stackctl deploy --target prod-hosted` 事务；不得新增环境名或第二执行面。
- 发布前真实远端复验统一收敛到 `prod-hosted` 的 `canary`，不引入 `prod-gray` 第二环境，且失败时不得写入成功事实。
- 五个 rollout stage 必须位于同一个保留 production approval 的事务 job；ReleaseEvidenceManifest 拉取、验签、治理校验和逐服务配置包物化只执行一次。
- 正式 apply 按 `canary -> 5 -> 20 -> 50 -> 100` 执行并复用 hosted ledger；任一 SLO、health、inspect、doctor、placement coverage 或 integration probe 失败，由 `stackctl` 回滚到 `fromCandidateDigest`。
- dry-run 不写 hosted ledger，只允许完成 `canary` 只读校验并明确报告 `5/20/50/100` 未执行，不得生成正式发布回执。
- 生产晋级与恢复只比较 `fromCandidateDigest/toCandidateDigest`；镜像 transport tag 与配置包路径/摘要只用于实际装配。
- workflow 创建后达到 1500 秒时不得开始下一 rollout stage；整个主链超过 1800 秒即失败，600 秒以上必须标记 `released_over_soft_budget`。
- Portal 与人工命令都必须进入受保护 runner 的同一强类型 `stackctl deploy --target prod-hosted ...` 请求入口；Portal 只提交并回读候选、目标阶段与证据引用，不执行脚本、不直接调用 Platform Ops 激活 command、不直接切流，也不保存第二份 rollout 状态。只有该 runner 中的 `stackctl` service principal 可以 exact-byte 消费已批准请求并向 Platform Ops 提交流量激活 effect。
- Platform Ops 为每次 effect 生成不可变签名 revision，并以 expected previous revision 对 active pointer 执行 compare-and-swap；`api-edge` 只读取该签名 active revision，在完整验签后原子切换且无需重启，并按实例回报绑定 revision、候选与策略摘要的 effective ACK。
- Platform Ops 只有在目标 `api-edge` 实例 ACK 同一 revision 后才能生成成功 activation receipt，`stackctl` 只能从该 authority 回读。该 receipt 与 deployment receipt 分离，绑定同一 candidate、previous/current revision、campaign、stage、策略摘要、SLO 决定、ACK 摘要与时间；任一缺失或漂移不得提升阶段。
- `5 / 20 / 50 / 100` 只改变 Platform Ops activation revision；不得重新构建、重签或改写 APK、镜像、环境配置包、ContractGraph 或候选身份，也不得通过 IaC 动态字段、API Edge restart 或旧 YAML fallback 生效。
- production approval 分段计时只接受绑定当前 repository、workflow run、head SHA、candidate digest 与 `production` environment 的 durable review event；Deployment/Deployment Status 的 `pending/queued/in_progress` 不得被解释为 reviewer 请求或批准时刻。
- 当前私有仓套餐不支持原生 required reviewers 时，唯一替代路径是受控 GitHub App/webhook 接收官方事件并写入独立 hosted append-only approval authority。接收面必须验证 GitHub webhook 签名、delivery ID 幂等、event/action 闭集、installation/repository/environment/run/head SHA/candidate/reviewer 绑定与 request→approved 顺序；workflow 只消费 hosted exact-byte readback。
- 外部 approval authority 不得声明或暗示原生 branch protection/environment protection 已启用；回执必须显式 `nativeProtection=false` 与 `enforcement=external_hosted_ledger`。缺 webhook、签名、request 或 approved 任一事实时保持 `historical_incomplete + GATE_BLOCK`。

## 4. 契约引用

- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 灰度发布到生产

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“灰度发布到生产”对应的公开行为。
- THEN **统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- AND 受控正式发布只申请一次 production approval、只物化一次 canonical evidence，并在同一事务 job 内依次执行 `canary、5、20、50、100`。
- AND 当前套餐下 request/approved 由验签 GitHub webhook 写入 hosted append-only authority，workflow exact-byte 回读同一 candidate；该事实明确不冒充原生 protection。
- AND Portal 或人工命令只向受保护 runner 提交同一强类型 `stackctl` 请求，Portal 不直接调用 Platform Ops 或执行 effect；runner 中的 `stackctl` exact-byte 消费已批准意图并保持唯一发布与激活执行入口。
- AND 每次阶段推进产生 Platform Ops 签名 active revision；`api-edge` 无需重启即可原子应用，并由全部目标实例 ACK 同一 revision、candidate 与 policy digest 后，`stackctl` 才能回读独立 activation receipt。
- AND `canary → 5 → 20 → 50 → 100` 全程 candidate、App/Cloud bytes、环境配置包与 ContractGraph 摘要不变，后四个阶段的 builder invocation 为零，且不存在 IaC 动态字段或 YAML fallback reader。
- AND dry-run 只读且不会伪造 `5/20/50/100` ledger；正式 apply 的失败会产生绑定候选摘要的 rollback 回执。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：生产灰度口径已统一为 prod rollout stage，不再出现 prod-gray 第二环境。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

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
- 影响或价值：尚缺少能够证明“灰度发布到生产”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
