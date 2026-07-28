# L2 Business Capability：产品运营控制面基础 (`product-control-plane-foundation`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一产品事件、实验、反馈优化与发布治理

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“product-control-plane-foundation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一产品事件、实验、反馈优化与发布治理。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`app-release-recovery-routing`](./app-release-recovery-routing/spec.md)：公开版本查询只按平台、可见版本和 Build 返回已发布事实；公众 iOS 指向趣我圈 PWA 安装与网页版通道，Android 指向趣我圈官网签名 APK 下载通道。
- [`product-control-plane-contract`](./product-control-plane-contract/spec.md)：每个控制面动作必须声明 operation scope；危险动作必须记录操作者、目标、原因、revision 与结果，失败时不得生成成功审计。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 product control plane foundation 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“统一产品事件、实验、反馈优化与发布治理”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 各领域 product-control-plane 的统一接口契约

- 各领域 `product-control-plane` 的统一接口契约
- 审核、处罚、申诉、恢复的统一 case / workflow 模型
- 推荐运营在召回、粗排、精排/重排的统一干预边界
- `ops.*` 与端侧 IA / 体验配置的统一边界
- 各领域手写各自的运营接口，无法统一 codegen
- 申诉与恢复缺少统一证据、SLA、双签与审计模型
- 统一运营控制面的直接使用者：运营、内容治理、客服、推荐策略维护者
- 当前组织模式下，上述角色可由全栈研发兼职承担，因此产品必须支持少角色拆分的协作方式
- 为 `product-ops` 统一运营控制面建立共同产品基线，第一阶段作为一个产品交付，内部包含“治理处置”和“增长/实验/推荐运营”两大模块。
- 为每个领域定义 `product-control-plane` 的统一管理接口规范，要求通过 `control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 表达，并由 codegen 生成 Web / Go / Python / App 契约。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 product control plane foundation 能力 SIT

- GIVEN 执行“product control plane foundation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“product control plane foundation 能力”对应动作。
- THEN 直属 Story 共同交付“统一产品事件、实验、反馈优化与发布治理”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 product control plane foundation 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一产品事件、实验、反馈优化与发布治理。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 首发内容供给、创作者激活与客服运营

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：校园、旅行、住宿、路线和对象点评内容包仍需明确负责人和真实生产；种子创作者、激活规则、FAQ、客服入口与值班表需要运营执行。
- 完成判定：内容 release 通过数据工程验收并绑定对象
- 创作者任务和影响力反馈可观测
- FAQ/客服入口可达且处置 SLA、值班 owner 明确。
- 依赖：内容运营、种子创作者与客服人力。
