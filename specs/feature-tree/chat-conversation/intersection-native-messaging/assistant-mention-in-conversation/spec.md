# L3 Story：会话内小趣答疑 (`assistant-mention-in-conversation`)

> 所属能力：[`intersection-native-messaging`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为在群里讨论去哪拍、用什么器材的用户，
我希望直接 @小趣 就能得到基于我们正在聊的内容和刚才分享的对象的回答，
从而不必退出会话另开一个助手窗口再把上下文复述一遍。

## 2. 范围与非目标

### In Scope

- 群会话内 @小趣 的结构化提及与事件触发。
- 会话上下文与被引用对象事实的注入范围。
- 助手回复回群与引用边界的可打开性。

### Out of Scope

- 助手的技能编排与回答生成，由 `assistant-run-learning` 负责。
- 助手作为会话成员的加入与移除，由 `list-detail-message-delivery` 的 `assistant-in-conversation` 负责。
- 垂类专有技能：垂类知识经既有技能的标签绑定表达，本节点不引入垂类专有技能。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 提及必须结构化并触发事件

- 群会话内 @小趣 必须产生结构化提及并触发助手提及事件；不得仅作为文本插入。
- 同一条提及最多触发一次回复，重发不产生重复回复。

<a id="req-002"></a>
### REQ-002 上下文注入范围明确且有界

- 注入助手的上下文限于最近消息窗口与会话内被引用对象的标签与交集事实；不得注入会话成员的私有资料或超出窗口的历史。

<a id="req-003"></a>
### REQ-003 回复必须回群且引用可打开

- 助手回复必须回到发起提及的同一会话，并给出可打开的引用边界。

<a id="req-004"></a>
### REQ-004 垂类知识不引入垂类专有技能

- 垂类知识必须经既有技能的标签绑定表达；不得为某个垂类新增专有技能或专有回复分支。

<a id="req-005"></a>
### REQ-005 助手不可用时不伪造回复

- 助手域不可用时必须给出结构化不可用；不得产生无依据的回复或静默丢弃提及。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/fields.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/fields.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 群内提及基于会话上下文回复

- GIVEN 群会话中已分享过一个对象，且成员随后 @小趣 提问。
- WHEN 助手提及事件被消费。
- THEN 助手在同一会话内回复，回复基于最近消息窗口与该被引用对象的事实，并给出可打开的引用。
- AND 同一条提及不产生重复回复。

<a id="gwt-002"></a>
### GWT-002 助手不可用时给出结构化不可用

- GIVEN 助手域当前不可用。
- WHEN 成员在群会话中 @小趣。
- THEN 会话内出现结构化不可用终态。
- AND 不产生无依据回复，提及也不被静默丢弃。

## 6. 依赖

- 前置要求：[`intersection-native-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 四环境真实回群链路尚未验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 alpha/beta/gamma/prod 同一候选上的真实身份、可靠事件、回复回读、结构化不可用和回滚证据；Chat `conversationId` 与 Assistant `sessionId` 已在契约、运行时、生成物和测试中物理分离，消费者与回群写入已有 local/API integration 证据。
- 完成判定：`GWT-001` 与 `GWT-002` 在四环境 Remote composition 上产生候选绑定的 CaseResult、消息回读、事件水位、告警与回滚证据。
