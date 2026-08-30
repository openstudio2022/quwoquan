# L2 Business Capability：统一控制面基础 (`runtime-control-plane-foundation`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-control-plane-foundation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`domain-onboarding-acceptance-governance`](./domain-onboarding-acceptance-governance/spec.md)：不存在第二真相源，且统一门禁能够发现路径、拓扑、配置和证据漂移。
- [`human-authority-role-cards`](./human-authority-role-cards/spec.md)：Human Authority 可在 Ops Portal 通过无偏置、可访问且可恢复的四类角色卡独立提交输入，而 Portal 不拥有决定语义或 effect。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime control plane foundation 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口

- 为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 冻结端侧可配置边界：一级/二级 tab、栏目、版面、布局与体验类 feature flag 可配置，但 long-polling 周期、超时、限流、采样率等运行时参数必须归入 `sys.*`。
- 统一门户视觉与交互语义必须匹配应用的 canonical 语义风格体系，不允许演化出割裂的第二套产品语义。
- 冻结统计仪表盘能力为统一门户的内建能力，支持总览、系统治理、实验归因、推荐效果、治理效率与审计追踪等多类 dashboard。
- 发布与验收责任人：通过统一门户完成跨域审计、变更跟踪与统一集成验收
- 统一入口承接 `platform-ops` 与 `product-ops` 的共同壳层能力
- 领域服务尚未形成三类面统一契约，后续拆分部署风险高
- 控制面对象、元数据、codegen、端侧 IA 配置、运行时参数尚未统一成单一真相源
- 门户、元数据、codegen、部署组合与统一集成验收都能进入开发而不需要返工大改
- `总览` 必须提供跨域经营与治理总览 dashboard：活跃告警、待办审批、发布状态、重点实验、治理 case、SLA 风险

<a id="req-003"></a>
### REQ-003 Human Authority 角色卡 Portal 接线

- Ops Portal 必须作为 Human Authority 四类角色卡的主展示与 submission 入口，消费 canonical Human-Agent contract 与 hosted authority readback；Portal 不拥有 Human 决定语义，不派生授权，不执行 effect。
- 角色卡必须保持 Round 1 / Round 2 独立输入、对称无推荐偏置、补证据、转交、暂停、超时与离线 readback 恢复，并以 OIDC/MFA UX 配合服务器端 principal、role、scope 与 SoD 强制边界。
- 工程根固定为 `quwoquan_ops/portal`；导航 authoring source 固定为 `quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`，Portal 只消费 generated projection，生成物禁止手改。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime control plane foundation 能力 SIT

- GIVEN 执行“runtime control plane foundation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime control plane foundation 能力”对应动作。
- THEN 直属 Story 共同交付“为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口”，失败终态可区分且不产生伪成功事实。
- AND Human Authority 角色卡以 canonical 投影展示并由服务器端校验 submission；错误角色、SoD 失败、重复、离线或超时均保持可恢复且不产生隐式批准或 effect。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime control plane foundation 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 Human Authority 角色卡跨 Story 集成尚未闭合

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：角色卡、generated 菜单、hosted authority 本地 provider/adapter 与 Portal test/build 已闭合，但统一门户仍缺正式 hosted identity/infrastructure、OIDC/MFA 双 principal、durable hosted submission/readback 与真实角色 UAT 的同一候选 evidence；这些外部证据闭合前不能宣称 authority 闭环完成。
- 完成判定：`SIT-001.t2` 由已闭合的本地分层证据与真实双 MFA 账号 UAT 共同满足，且机器证据不替代 hosted 人类验收。
- 依赖：[`human-authority-role-cards/OPEN-001`](./human-authority-role-cards/spec.md#open-001) 与 [`hosted-human-authority/OPEN-002`](../../platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#open-002)。
