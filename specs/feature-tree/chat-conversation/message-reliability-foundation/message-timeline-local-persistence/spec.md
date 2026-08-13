# L3 Story：消息时间线本地落盘 (`message-timeline-local-persistence`)

> 所属能力：[`message-reliability-foundation`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为已经用过某个会话的用户，
我希望冷启动或断网时打开会话仍能读到最近的历史消息，
从而不会因为一次网络失败就失去整段对话上下文。

## 2. 范围与非目标

### In Scope

- 会话打开时先水合本地时间线、再后台刷新的顺序。
- 本地副本的写入时机：远端拉取结果、实时推送与本地待发消息。
- 缓存读取来源的可区分性：本地命中、后台刷新中、离线只读、本地待发。

### Out of Scope

- 历史向上翻页，由 [`message-paging-and-ordering`](../message-paging-and-ordering/spec.md) 负责。
- 断连缺口补齐，由 [`realtime-push-and-offline-sync`](../realtime-push-and-offline-sync/spec.md) 负责。
- 会话列表缓存，由 `chat-experience-optimization` 的 `chat-list-local-cache` 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话打开必须先水合本地再刷新远端

- 会话打开必须以本地副本作为首帧内容来源；远端刷新在其后进行且不得清空已展示内容。
- 本地为空且远端失败时必须呈现可重试失败态，不得以空列表表达「没有消息」。

<a id="req-002"></a>
### REQ-002 本地消息存储唯一

- 消息本地写入必须落到既有 chat 本地库；不得新建第二个消息存储，搜索与时间线必须读同一份消息行。
- 本地副本必须遵守 [`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)，字段只从 chat-service canonical Message 契约派生，不维护对象策略台账。

<a id="req-003"></a>
### REQ-003 缓存来源必须可区分且驱动展示

- 缓存读取结果必须能区分本地命中、后台刷新中、离线只读与本地待发；端侧据此分流展示，不得把离线只读与刷新失败混为同一态。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/fields.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 冷启动离线打开会话可读历史

- GIVEN 设备曾同步过某会话且当前无网络。
- WHEN 用户冷启动应用并打开该会话。
- THEN 时间线由本地副本水合并按 seq 有序展示，来源为离线只读。
- AND 不出现空列表或错误页冒充「没有消息」。

<a id="gwt-002"></a>
### GWT-002 本地为空且远端失败呈现可重试失败态

- GIVEN 设备从未同步过某会话且远端请求失败。
- WHEN 用户打开该会话。
- THEN 返回 canonical failure 并呈现可重试入口。
- AND 不写入任何本地成功事实。

## 6. 依赖

- 前置要求：[`message-reliability-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 本地时间线落盘剩冷启动真实读回证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺真机 UAT 层「杀进程重启后离线打开会话可读」的旅程证据。
  真实 SQLite 磁盘文件的跨实例冷启动读回已有 api_integration 证据，由
  `message_timeline_cold_start__api_integration_test.dart` 断言新 store 实例读回
  seq 升序完整恢复、分页游标语义保持与 persona scope 隔离。撤回消息在本地副本
  写 recalled 占位而非物理删除、离线重开仍可见占位，由
  `chat_send_failure_recovery__local_contract_test.dart` 断言。
  本地水合→远端刷新→写回本地副本的链路已实现并有 local_contract 证据
  （`message_timeline_persistence_paging__reliability__local_contract_test.dart`）：
  本地命中且远端失败表达为离线只读来源（会话页展示离线提示条、不清空内容、不与刷新失败混态），
  本地为空且远端失败呈现可重试失败态且不写入本地成功事实；本地
  存储复用搜索 SQLite 单库（`chatMessageTimelineCacheProvider` → search index adapter）。
- 完成判定：`GWT-001` 的冷启动语义由真实持久库跨进程读回测试证明；`GWT-002` 已闭合。
