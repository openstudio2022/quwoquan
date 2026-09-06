# L2 Business Capability：配置与可靠性治理 (`config-and-reliability-governance`)

> 所属领域：[`platform-ops-governance`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让平台运维通过同一控制面治理配置来源、服务可靠性、发布灰度和环境依赖，并获得可审计、可回滚的操作结果。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“config-and-reliability-governance”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`config-source-governance`](./config-source-governance/spec.md)：系统必须由 config schema 与单个环境 overlay 合成服务有效配置，并以 revision 与摘要识别发布内容，且失败时不得写入成功事实。
- [`hosted-human-authority`](./hosted-human-authority/spec.md)：以独立 hosted provider 承载真实人员认证、append-only Human Decision、签名 exact-byte readback 与单次 consume/revoke，为 Objective 与生产审批提供 fail-closed authority。
- [`reliability-policy-control`](./reliability-policy-control/spec.md)：用 SLO、错误预算、kill-switch 和回滚阈值约束高风险配置与服务发布。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 配置与可靠性治理能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力

- 承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 为各领域的 `platform-control-plane` 提供统一接入模型，要求通过 `control_plane.yaml` 与 `config_schema.yaml` 等元数据声明，并由 codegen 生成契约。
- 控制面契约必须独立于用户面 API，不得依赖当前同 Pod 部署。
- 高风险配置必须具备灰度、回滚、审计与危险动作确认能力。
- 各领域接入时必须声明最低 `platform-control-plane` 对象集合。
- 本地 runtime 生命周期必须消费 `config-source-governance` 输出的唯一资源所有权结果，只收敛目标 runtime 自有资源并保持独立控制面在场；所有权无法唯一裁定或目标自有资源未收敛时不得产生成功终态。

<a id="req-003"></a>
### REQ-003 Hosted Human Authority 必须独立认证、持久化并可精确消费

- 本能力必须通过 [`hosted-human-authority`](./hosted-human-authority/spec.md) 组合 Human canonical policy 与 Objective consumer：Platform Ops 只拥有 hosted provider wire、身份验证、append-only aggregate、签名/exact-byte readback、consume/revoke、storage/outbox/retention，不复制 Human role、DecisionKind、职责或 SoD 闭集。
- 生产关键决定必须按 Human policy 使用不同 authenticated principals，不能因小团队降级；Portal session、自报 role、Reviewer PASS、本地 provider/projection 或 GitHub job 状态均不能生成 executable authority。
- hosted authority 未实现或正式 GitHub App、hosted DB/signing key、OIDC 与真实 MFA principals 未闭合时，本能力必须保持 authority readiness blocked。

## 6. 契约与依赖

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 config and reliability governance 能力 SIT

- GIVEN 执行“config and reliability governance 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“config and reliability governance 能力”对应动作。
- THEN 直属 Story 共同交付“承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力”，失败终态可区分且不产生伪成功事实。
- AND 本地 runtime 生命周期只收敛目标自有资源并保持独立控制面在场；所有权无法唯一裁定或目标自有资源未收敛时不得产生成功终态。

<a id="sit-002"></a>
### SIT-002 单文件 stdin pipe 契约脚本的规模治理单轨归 Code Health Delta

- GIVEN 某 Python 脚本被 ops shell 编排以整文件 stdin pipe 到远端裸 `python3 -` 执行（远端不存在仓库树，如 `quwoquan_ops/cli/prod/sync_prod_plane_stack.sh` 之于 `hosted_release_ledger.py`），单文件自包含是物理设计契约。
- WHEN 治理门评估该脚本的文件规模。
- THEN 唯一判罚来源是 canonical Code Health Delta 的 `thresholds.file_lines`（新越过 block 或既有超限继续增长才 `GATE_BLOCK`），Python 脚本治理不维护第二套行数预算、人工 allowlist 或机器派生豁免，单文件契约脚本与其余手写生产文件适用同一阈值。

<a id="sit-004"></a>
### SIT-004 Hosted Human Authority 身份、决定与 Objective 消费闭环

- GIVEN Human canonical contract 已提供目标 DecisionUnit 的 role、DecisionKind、职责与 SoD，且正式 hosted provider、OIDC、GitHub App、signing key 与 Objective consumer 均可用。
- WHEN 两个或更多适用的真实 MFA principals 经 Portal/GitHub ingress 完成两轮 seal、决定、签发、exact-byte readback、consume 或 revoke，并注入断连、乱序、重放、篡改、过期与竞争。
- THEN Platform Ops 只在自身边界内原子保存 append-only decision/audit/outbox/receipt，Human policy 闭集不被复制或降级。
- AND Objective 只有 exact-byte verifier 全部通过后的单一 consume winner 可以进入 effect；revoke 先行与全部负例均 fail-closed、零越权 effect。
- AND local test provider 与 projection 只形成 non-release evidence；正式前置或 live UAT 缺一项时 authority readiness 保持 blocked。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 config and reliability governance 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 Hosted Human Authority 能力级集成尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前尚缺正式 hosted identity/infrastructure 与 live UAT evidence，本 L2 不能声明 hosted authority ready；provider contract、Go/PostgreSQL provider 与 Objective hosted adapter 的本地实现证据已闭合。外部前置由 [`hosted-human-authority/OPEN-002`](./hosted-human-authority/spec.md#open-002) 在最低可关闭节点拥有。
- 完成判定：该 L3 外部 OPEN 关闭，`SIT-004` 由同一 immutable candidate 的 api_integration/user_acceptance 直接绑定，且 local/projection evidence 不被提升为 release evidence。
