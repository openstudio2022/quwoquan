# L3 Story：全局搜索交集消费 (`search-intersection-consumption`)

> 所属能力：[`cross-domain-search`](../spec.md)

> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，
我希望connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句，
从而找到可理解并可继续操作的结果。

## 2. 范围与非目标

### In Scope

- “全局搜索交集消费”的输入、可观察主路径、失败语义以及与父能力的交接。
- 搜索 hit connectionState + intersectionReason 契约。
- 交集 Tab / 今日交集 / 发现区交集分组 UI。
- G2 primaryText 只读展示。
- 云侧 search read model 全量。
- 端侧文案拼装。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 全局搜索交集消费

- connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句。

<a id="req-002"></a>
### REQ-002 搜索交集结果分组互斥

- connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句。

<a id="req-003"></a>
### REQ-003 端侧本地拼装交集文案（G2 禁止）

- 端侧本地拼装交集文案（G2 禁止）。
- connectionState 分组与 global-search-experience spec 已连接/发现区规则一致；**缺 connectionState 的 hit 不进入交集展示窗**（零过渡，禁止客户端推断）。

## 4. 契约引用

- canonical：`_shared/search_contract.yaml`
- canonical：`_shared/search_objects.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 全局搜索交集消费

- GIVEN 执行搜索的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“全局搜索交集消费”对应的公开行为。
- THEN connected / discovery / intersection_lead 三组互斥，connected 区不展示交集句。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
