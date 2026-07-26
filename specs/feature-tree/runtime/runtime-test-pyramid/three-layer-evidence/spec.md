# L3 Story：三层测试证据追踪 (`three-layer-evidence`)

> 所属能力：[三层测试模型](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；证明各层 UAT/DOM/SIT/GWT 是否真实达成
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发者或审核者，我希望从节点验收直接找到职责匹配的测试，并能区分未完成验收与环境阻断，从而不把文件存在或单层绿灯误报为准出。

## 2. 范围与非目标

### In Scope

- local_contract、api_integration、user_acceptance 三层目录与 `spec_ref` 双向校验。
- 无证据验收必须由同节点 OPEN 声明；环境缺失必须保留 GATE_BLOCK。

### Out of Scope

- tracked coverage map、证据索引、测试排列组合和历史运行台账。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 验收与真实证据双向一致

- 已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。

## 4. 契约引用

- trace gate：`quwoquan_ops/cli/feature_tree.py`
- test layout：`quwoquan_ops/gate/scaffold/verify_test_directory_layout.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 区分真实证据与开放事项

- GIVEN 一个验收有直接测试引用，另一个验收仅在同节点 OPEN 的完成判定中出现。
- WHEN 三层测试追踪门禁扫描规格与测试。
- THEN 前者计为证据，后者保持未完成；不存在的锚点、错误测试层或悬挂引用被阻断。

## 6. 依赖

- 前置要求：节点验收 ID 稳定，测试目录采用 canonical 三层名称。
- 上游事实：spec 验收、OPEN 和测试 `spec_ref`。
- 下游结果：可执行证据关系或 GATE_BLOCK。
- 父级设计：`DEC-001`
