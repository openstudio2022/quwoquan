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

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 config and reliability governance 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：承接 `platform-ops` 的平台运维控制面规格，负责把“配置治理 + 服务治理 + 发布灰度 + 环境依赖”沉淀为可设计、可实现、可验收的统一平台能力。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
