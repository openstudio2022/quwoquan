# L3 Story：搜索聚合分区的“讨论”命名与 Circle facet (`circle-facet-search-and-filter`)

> 所属能力：[`cross-domain-search`](../spec.md)

> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望搜索聚合分区使用“讨论”、消息会话使用“群聊”、
Circle 对象使用“圈子”，从而在筛选和打开结果时不会混淆三种不同对象。

## 2. 范围与非目标

### In Scope

- 搜索结果页的讨论分区与 Circle 分类 facet。
- `circle.group`、`circle.circle` 和 `chat.conversation(group)` 的用户侧命名边界。

### Out of Scope

- Circle 聚合、圈子管理或群聊会话的写模型。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 搜索聚合分区统一使用“讨论”

- 跨 `circle.group` 与 `circle.circle` 的搜索聚合分区统一显示“讨论”。
- 消息域 group 只显示“群聊”，Circle 对象仍显示“圈子”；不得恢复“群组”“趣群”“讨论群”等并行别名。

<a id="req-002"></a>
### REQ-002 Circle facet 只消费 Circle 域分类投影

- 讨论 facet 的真相源必须来自 Circle 域已有分类与配置模型。
- 搜索域不得新增 channel、forum 或第二套分类对象。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 搜索讨论分区与对象命名保持单轨

- GIVEN `search_objects.yaml` 登记 `circle.group`、`circle.circle` 与 `groups` 分区。
- WHEN App 生成并渲染搜索对象、筛选项和聚合分区。
- THEN `groups` 分区显示“讨论”，消息 group 显示“群聊”，Circle 对象显示“圈子”。
- AND 搜索 metadata 与用户可见文案不出现“群组”“趣群”“讨论群”等退役别名。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
