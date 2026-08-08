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

<a id="req-003"></a>
### REQ-003 Circle Remote 搜索源保持强类型、稳定分页与可见性边界

- `circle.circle.SearchCircles` 是 Circle 搜索 facet 的 production Remote source；已认证 Persona 的非空查询与分类筛选必须返回 canonical 强类型搜索结果，不得由页面或本地索引重建远端结果。
- 查询词与分类筛选的 canonicalization、候选资格、排序和游标分页由 Circle owner 解释；App 只保留服务端顺序和下一游标，不得本地重排、重新过滤或跨页补造命中。
- 结果只包含调用主体可见且仍具公开搜索资格的 Circle；不可见、处于归档状态或无权访问的对象不得因筛选值、游标或重试被探测，非法输入、身份或依赖失败必须返回 operation-bound canonical failure。
- typed local fallback 与跨领域页面复合终态只表达各自层的降级或组合结果，不构成 `SearchCircles` source readiness 证据。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 搜索讨论分区与对象命名保持单轨

- GIVEN `search_objects.yaml` 登记 `circle.group`、`circle.circle` 与 `groups` 分区。
- WHEN App 生成并渲染搜索对象、筛选项和聚合分区。
- THEN `groups` 分区显示“讨论”，消息 group 显示“群聊”，Circle 对象显示“圈子”。
- AND 搜索 metadata 与用户可见文案不出现“群组”“趣群”“讨论群”等退役别名。

<a id="gwt-002"></a>
### GWT-002 SearchCircles production Remote source 合同

- GIVEN 已认证 Persona 提交非空查询与 Circle 分类筛选，且候选集中同时存在跨页公开命中、不可见对象、处于归档状态的对象和不匹配对象。
- WHEN 通过 canonical `circle.circle.SearchCircles` source 首次查询、继续分页，并在可恢复失败后按原查询上下文重试。
- THEN 返回非空强类型 Circle 搜索结果；首尾页保持服务端稳定顺序与游标连续性，无重复、遗漏或本地重排，语义等价的查询与筛选经 owner canonicalization 收敛到同一合格候选集。
- AND 只返回调用主体可见且仍具公开搜索资格的 Circle；猜测筛选值或游标不能暴露不可见、处于归档状态或无权访问对象的存在与字段。
- AND 非法查询、身份拒绝或依赖失败返回与 `SearchCircles` 绑定的 canonical failure；重试保持原查询、筛选和游标语义，不把错误或空 payload 解码为成功。
- AND 本地 fallback 命中、页面路径存在、跨领域聚合结果或页面可恢复终态均不得冒充本 source 的成功证据。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 SearchCircles source readiness 尚缺对象级直接证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前尚无对象级 App local_contract 直接证明 `SearchCircles` 的强类型非空结果、稳定分页、筛选 canonicalization、可见性边界与 canonical failure；既有本地 fallback 或页面复合测试不能替代 source 合同。
- 完成判定：`GWT-002.t1`、`GWT-002.t2`、`GWT-002.t3`、`GWT-002.t4` 均被真实对象级测试直接绑定，且证据来自同一 production Remote 与 generated operation source。
- 依赖：Circle owner 的 canonical operation、production Remote composition 与可恢复失败语义保持单轨。
