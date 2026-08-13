# L3 Story：主页搜索候选列表与发布挂载选择器的最小闭环 (`homepage-search-and-picker`)

> 所属能力：[`homepage-discovery-and-attach`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护共享主页的用户，我希望主页搜索候选列表与发布挂载选择器的最小闭环，从而在不丢失当前上下文的前提下完成主页发现、治理或互动。

## 2. 范围与非目标

### In Scope

- 主页搜索输入、候选结果摘要（名称/类目/城市/评分摘要）。
- 选择器选中后返回 HomepagePickerSelectionResult 回填发布上下文。

### Out of Scope

- 搜索无结果时的补充主页流程（missing-homepage-suggestion-and-review）。
- 主页详情完整消费。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 用户搜索主页并在选择器中确认候选

- picker 页 loading/error/empty/populated 四态齐备且选择结果可回填。

<a id="req-002"></a>
### REQ-002 前台统一使用“主页”和具体类目名

- 前台统一使用“主页”和具体类目名。
- 搜索结果必须能区分高频同名主页。
- 选择器必须支持返回当前上下文，而不是打断主流程。
- 如搜索稳定性不足，可短期关闭主页挂载入口，但不能破坏主页本身浏览。

## 4. 契约引用

- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户搜索主页并在选择器中确认候选

- GIVEN 已发布主页存在于搜索投影（fixture entity_homepage_core 或 gamma seed）。
- WHEN 用户在 homepagePicker 输入关键词并点击候选。
- THEN 候选列表展示名称、类目、城市与评分摘要，可区分同名主页。
- THEN 选中后以 HomepagePickerSelectionResult 返回调用方，原上下文不丢失。
- THEN 搜索失败/空结果展示结构化错误态或空态，不回退假数据。

## 6. 依赖

- 前置要求：[`homepage-discovery-and-attach`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 用户搜索主页并在选择器中确认候选

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：picker 页 loading/error/empty/populated 四态齐备且选择结果可回填。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 主页搜索的拼音与同义词信号只存在于测试替身,生产读面无此行为

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `/homepages/search` 的拼音首字母（如 `scly`）与同义词（如 `出行`）扩展只内嵌在 entity-service 测试 memory reader 的 `rtsearch.Execute` 里，生产组装的 Mongo reader 只有 `$text` 全文索引——旧测试证明的是生产 HTTP 上不存在的行为，已改写为 `$text` 命中与候选隔离的真实断言。信号能力的真实落点需在「搜索投影 → search-service 链路」与「Mongo reader 接入 rtsearch」之间裁决（suggest 归属见 `search-storage-topology-and-elasticity` 的既有裁决）。
- 完成判定：`GWT-001` 的搜索命中行为在生产组装读面上具备拼音首字母与同义词信号，且真实 api_integration 测试 `spec_ref` 断言该行为经生产 reader 成立，不接受 memory reader 证据。
