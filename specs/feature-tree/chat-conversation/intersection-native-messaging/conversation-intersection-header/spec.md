# L3 Story：会话头部交集摘要 (`conversation-intersection-header`)

> 所属能力：[`intersection-native-messaging`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-003](../design.md#dec-003)

## 1. 用户价值

作为在 1v1 会话里聊天的用户，
我希望随时能看到我和对方是怎么连上的，
从而在聊天冷场或时隔很久重新打开时仍有话题可循。

## 2. 范围与非目标

### In Scope

- 1v1 会话头部的交集摘要来源与展示上限。
- 由破冰升级而来的会话中破冰依据的保留。
- 群会话不展示交集头部这一边界。

### Out of Scope

- 破冰依据的写入与重解析，由 [`greeting-intersection-context`](../greeting-intersection-context/spec.md) 负责。
- 会话头部的其他信息与操作入口，由 `list-detail-message-delivery` 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 仅 1v1 会话展示交集头部

- 交集摘要只在 1v1 会话头部展示；群会话头部不得展示交集摘要。

<a id="req-002"></a>
### REQ-002 摘要内容与展示上限

- 摘要必须来自云侧交集聚合，最多展示两个具体交集点，不得以聚合计数表述代替具体内容。

<a id="req-003"></a>
### REQ-003 破冰依据在升级后保留

- 由打招呼升级而来的会话必须保留其破冰依据；该依据不随会话时间推移而消失。

<a id="req-004"></a>
### REQ-004 无交集时不占位

- 双方无成立交集且无破冰依据时，会话头部不展示交集区域，也不展示占位文案。

<a id="req-005"></a>
### REQ-005 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/intersection_action_hint.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 1v1 会话头部展示交集且群会话不展示

- GIVEN 当前用户分别处于一个有成立交集的 1v1 会话与一个群会话。
- WHEN 用户依次打开这两个会话。
- THEN 1v1 会话头部展示最多两个具体交集点，群会话头部不展示交集。
- AND 展示内容整体来自云侧。

<a id="gwt-002"></a>
### GWT-002 破冰升级而来的会话保留依据

- GIVEN 一个由携带依据的打招呼升级而来的 1v1 会话。
- WHEN 用户重新打开该会话。
- THEN 会话头部仍展示当初的破冰依据。
- AND 依据与请求箱中展示过的内容一致。

## 6. 依赖

- 前置要求：[`intersection-native-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-003](../design.md#dec-003)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 会话页尚无任何交集落地

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前会话页不展示任何交集信息，用户在时隔较久重新打开会话时无从回忆双方的连接理由，破冰依据在升级为正式会话后即丢失。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
