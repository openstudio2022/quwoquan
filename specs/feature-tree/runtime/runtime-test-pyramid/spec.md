# L2 Business Capability：三层测试模型 (`runtime-test-pyramid`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。

## 2. 范围与非目标

### In Scope

- 三层测试命名、case ID、环境语义和执行入口
- Journey/Page 到 local contract 与 api integration 的反向关联
- 物理目录扫描和运行报告计算

### Out of Scope

- 单个业务 Story 的具体产品行为
- 远端环境和凭证供给
- prod 审批与放量决策

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`three-layer-evidence`](./three-layer-evidence/spec.md)：已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 三层测试模型与门禁单轨收口

- 节点 spec 只登记稳定 UAT/DOM/SIT/GWT；测试或可执行治理门以 `spec_ref` 直接引用验收锚点。
- 已关闭验收至少有一个真实、职责匹配且可运行的 `spec_ref`；未闭合验收由同节点 OPEN 明确完成判定。
- App、Service、Data、Ops 的 canonical 三层目录是唯一测试入口。
- 运行报告从测试代码、执行结果、环境和制品摘要实时生成，不提交覆盖清单或证据索引。
- 视觉基线的 fixture 必须与执行日期无关；会跨越相对时间阈值的当前日期不得写入 golden 输入。

<a id="req-002"></a>
### REQ-002 禁止新增 T1-T4、L1-L4、contract-test 等第二套分层名称

- 禁止新增 `T1-T4`、`L1-L4`、`contract-test` 等第二套分层名称
- `spec_ref` 与验收锚点必须双向有效，禁止集中映射表或不存在的逻辑 case 冒充测试
- 缺少远端环境、凭证或当前报告时必须 `GATE_BLOCK`，不得以静态声明代替

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 三层测试模型与门禁单轨收口

- GIVEN 执行“三层测试模型与门禁单轨收口”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三层测试模型与门禁单轨收口”对应动作。
- THEN 节点 spec 不包含测试文件、命令、通过率或历史证据，测试代码以 `spec_ref` 直接关联稳定验收锚点。
- THEN 每个已关闭验收都有真实测试或可执行治理门反向引用；OPEN 中的未完成验收不会被误报为通过。
- THEN App、Service、Data、Ops 的 canonical 三层目录是唯一测试入口。
- THEN golden fixture 使用固定、跨执行日期稳定的输入，不因相对时间阈值自动漂移。
- THEN 动态报告能从当前代码与运行结果定位实际测试、环境和制品摘要，不读取 tracked inventory。
