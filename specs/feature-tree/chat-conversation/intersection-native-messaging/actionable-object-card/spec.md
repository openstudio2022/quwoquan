# L3 Story：可行动对象 card (`actionable-object-card`)

> 所属能力：[`intersection-native-messaging`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-029`](../../../spec.md#scn-029)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为把一个地方、一篇内容或一个约伴分享进会话的用户，
我希望会话里的人看到的是可以直接动手的卡片而不是一段链接文本，
从而讨论能就地变成行动而不用各自跳出去操作。

## 2. 范围与非目标

### In Scope

- 内容、主页、圈子与 Gathering 分享进会话后的 card 展示。
- card 行动按云侧行动键、路由类别与目标可达性分流。
- 不可承接行动的展示口径。

### Out of Scope

- 行动键闭集与可达性的定义，由推荐域 registry 负责。
- Gathering 的加入与名单治理，由 `circle-community` 的 `gathering-coordination` 负责。
- 富媒体消息的渲染，由 `list-detail-message-delivery` 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分享进会话的对象渲染为可行动 card

- 内容、主页、圈子与 Gathering 分享进会话后必须渲染为带行动的 card，不得退化为纯链接文本。

<a id="req-002"></a>
### REQ-002 行动分流只依据云侧契约

- card 的行动必须依据云侧登记的行动键、路由类别与目标可达性分流；端侧不得维护第二张行动到页面的映射表，也不得按垂类或具体交集类型分支。

<a id="req-003"></a>
### REQ-003 不可承接的行动展示为不可执行

- 目标可达性标记为不可承接时，该行动必须展示为不可执行的规划口径；不得渲染为可点击入口，也不得点击后进入空白页。

<a id="req-004"></a>
### REQ-004 可转发主体不包含交集本身

- 会话内可转发主体包含对象与 Gathering，不得包含交集本身；交集是双方之间的关系事实，不作为可转发主体。

<a id="req-005"></a>
### REQ-005 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/intersection_action_hint.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/fields.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 可承接与不可承接行动同时正确分流

- GIVEN 一个对象被分享进会话，其云侧行动提示同时包含可承接与不可承接的行动。
- WHEN 会话成员查看该 card。
- THEN 可承接行动可直接执行并到达真实承接页，不可承接行动展示为不可执行的规划口径。
- AND 不出现点击后无承接页的行动入口。

<a id="gwt-002"></a>
### GWT-002 交集不可作为转发主体

- GIVEN 用户在对象页看到一条与某人的交集。
- WHEN 用户尝试将其转发进会话。
- THEN 可转发主体只包含该交集指向的目标对象，不包含交集本身。
- AND 不产生以交集为主体的消息。

## 6. 依赖

- 前置要求：[`intersection-native-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 会话内尚无可行动 card

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前对象分享进会话后没有可行动 card，讨论无法就地转为行动，交集行动阶梯在会话内断开。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
