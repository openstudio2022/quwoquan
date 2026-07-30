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
- prod gray-initial 的 hosted deploy、只读/幂等 api_integration 与 Journey/Page user_acceptance。
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

- 系统必须只有一个 `prod` 生产环境；`gray-initial / carry-on / full` 只是同一 `prod-hosted` 目标的 rollout stage。
- 发布前真实远端复验统一收敛到 `prod-hosted` 的 `gray-initial`，不引入 `prod-gray` 第二环境，且失败时不得写入成功事实。
- 三个 rollout stage 必须位于同一个保留 production approval 的事务 job；ReleaseEvidenceManifest 拉取、验签、治理校验和逐服务配置包物化只执行一次。
- 正式 apply 按 `5% -> 25% -> 100%` 执行并复用 hosted ledger；任一 SLO、health、inspect、doctor 或 integration probe 失败，由 `stackctl` 回滚到 `fromCandidateDigest`。
- dry-run 不写 hosted ledger，只允许完成 gray-initial 只读校验并明确报告 carry-on/full 未执行，不得生成正式发布回执。
- 生产晋级与恢复只比较 `fromCandidateDigest/toCandidateDigest`；镜像 transport tag 与配置包路径/摘要只用于实际装配。
- workflow 创建后达到 1500 秒时不得开始下一 rollout stage；整个主链超过 1800 秒即失败，600 秒以上必须标记 `released_over_soft_budget`。
- production approval 分段计时只接受绑定当前 repository、workflow run、head SHA 与 `production` environment 的 durable review event；Deployment/Deployment Status 的 `pending/queued/in_progress` 不得被解释为 reviewer 请求或批准时刻。

## 4. 契约引用

- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 灰度发布到生产

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“灰度发布到生产”对应的公开行为。
- THEN **统一入口**：workflow 与人工命令最终都收敛到 `stackctl deploy --target prod-hosted ...`。
- AND 受控正式发布只申请一次 production approval、只物化一次 canonical evidence，并在同一事务 job 内依次执行 5%、25%、100%。
- AND dry-run 只读且不会伪造 carry-on/full ledger；正式 apply 的失败会产生绑定候选摘要的 rollback 回执。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 prod gray-initial 承接真实远端复验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：生产灰度口径已统一为 prod rollout stage，不再出现 prod-gray 第二环境。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 prod gray-initial 与自动回滚真实演练

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：CI 与 stackctl 接线不能替代真实 ACK 灰度、SLO gate 和回滚证据。
- 完成判定：通过 `stackctl deploy --target prod-hosted`，使用按 `edge / media / service / data` 平面隔离的 `PROD_*_SSH_KEY` 与发布 secrets，完成 `gray-initial -> carry-on -> full`、故障注入、SLO 阻断和自动回滚；全部证据绑定同一 candidate digest。
- 依赖：生产托管主机账号、各平面 SSH 凭据、渠道/数据面 secrets 与发布审批。

<a id="open-004"></a>
### OPEN-004 production approval durable review event

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：GitHub Deployment、Deployment Status 与 Actions review-history 的当前只读响应没有同时给出 required-reviewer 请求和批准的明确事件时间；用 `queued/in_progress` 或 Prod job `started_at` 替代会把 runner/concurrency queue 误算成审批，造成 timing 假绿。
- 完成判定：hosted release ledger 持久化显式 production review request/approved 事件及接收时间，并严格绑定 repository、workflow run、head SHA、environment 和 reviewer decision；`CiTimingSummary` 能据此生成 approvalRequestedAt、approvalApprovedAt、humanDecisionWait 与 approvalWait，且不再存在对应 `missingEvidence`。
- 依赖：GitHub 官方可订阅的 explicit review event、受控 GitHub App/webhook 接收面与 hosted ledger 不可变回读。

<a id="open-002"></a>
### OPEN-002 灰度发布到生产 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“灰度发布到生产”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
