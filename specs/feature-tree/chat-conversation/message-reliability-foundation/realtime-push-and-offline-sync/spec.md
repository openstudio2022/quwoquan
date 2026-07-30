# L3 Story：实时推送与离线同步（Realtime Push & Offline Sync） (`realtime-push-and-offline-sync`)

> 所属能力：[`message-reliability-foundation`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为参与会话的用户，
我希望在线时即时收到消息和成员变化，离线重连后按游标补齐缺口且不重复终态，
从而在网络切换和网关重连后仍看到完整一致的会话。

## 2. 范围与非目标

### In Scope

- “实时推送与离线同步（Realtime Push & Offline Sync）”的输入、可观察主路径、失败语义以及与父能力的交接。
- `RealtimeConnectionDelegate`、`RealtimeConnectionNotifier` 与 `realtimeConnectionManagerProvider` 的唯一 production Remote 入口。
- alpha/beta/gamma/prod 通过同一 composition root 注入 Remote delegate，环境 kernel 不可达任何 fixture delegate。
- `QuWoQuanAppRoot` 的 foreground/background lifecycle 接线。
- Remote idle long-poll、active websocket、background disconnect 的最小状态机闭环。
- 测试树 typed event double 驱动的 `MessageSent` 与 `ConversationMemberAdded` handler 契约。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 实时推送与离线同步（Realtime Push & Offline Sync）

- `ConversationMemberAdded` 必须进入独立 handler 分支，并生成可回读的群成员系统消息。

<a id="req-002"></a>
### REQ-002 测试树的 ConversationMemberAdded 事件能走统一 handler 分支

- 测试树 typed event 中的 `ConversationMemberAdded` 必须经与 Remote 共用的 handler 生成群成员系统消息。

<a id="req-003"></a>
### REQ-003 Remote foreground idle / active / background 状态切换可验证

- foreground idle、active 与 background 切换必须按 policy 建立或释放 Remote transport，不得遗留 timer。

<a id="req-004"></a>
### REQ-004 四环境 Remote 与 test-only double 物理隔离

- alpha/beta/gamma/prod composition 只能注入 Remote；typed double 只能由测试树直接装配，二者不得互相可达。

<a id="req-005"></a>
### REQ-005 环境 Mock 演示不可信，Remote 与本地 handler 证据必须分层

- **Mock 演示不可信**：Mock 只能切 transport state，不能推送 contract 对齐的新消息/入群事件，无法证明 handler 和 UI 更新链路。
- **background**：统一 `disconnected`，transport 全部释放。
- `RealtimeConnectionNotifier` 是 UI 层唯一可见入口；页面不得直接 new `LongPollTransport` / `WebSocketTransport`
- 四环境 realtime source 禁止 import alpha/mock package、fixture loader 或任意 mock 数据目录。
- 环境事件 payload 只来自 Remote gateway；测试事件只存在测试树，未登记会话不得由 runner/UAT 生成伪造 realtime 事件。
- Long-poll 请求路径与 page id 必须来自 `realtime_api_metadata.g.dart` 与 `realtime_request_page_ids.g.dart`
- Remote 与测试树 typed event 必须复用同一个 `RealtimeMessageHandler`，不得维护第二条消息插入链路。
- 测试树必须证明 `ConversationMemberAdded` 分支会产生系统消息。
- 页面卸载、退后台不得留下 leaked timer 或继续追加延迟推送；runtime mode 变化不得替换 realtime delegate。

<a id="req-006"></a>
### REQ-006 四环境 Remote 单轨连接与生命周期收敛

- 四环境必须使用 Remote-only realtime；测试 double 与环境 artifact 物理隔离，生命周期切换与聊天页更新经同一 handler 收敛。

<a id="req-007"></a>
### REQ-007 会话事件必须落持久流并支持按游标重放

- 会话事件在广播之外必须落持久流；断连期间产生的事件必须能在重连后按游标重放，不得只做即时广播。
- 长轮询请求必须携带游标，响应必须回执下一游标；游标越界必须返回 canonical failure 而不是静默从头开始。

<a id="req-008"></a>
### REQ-008 传输恢复必须发出真实事件并驱动补洞

- 传输层恢复必须发出可被端侧消费的恢复事件；不得保留无人发出的恢复分支或无人调用的补洞入口。
- 端侧收到恢复事件后必须以本地已持有的最大 seq 为起点向服务端补齐缺口；补齐结果与实时推送经同一去重路径合并。

<a id="req-009"></a>
### REQ-009 群 fan-out 必须批量且单点失败隔离

- 群会话事件分发必须批量进行；单个接收方分发失败不得中断整批分发。
- 网关扩缩必须由连接数与订阅积压驱动，并有对应告警。

## 4. 契约引用

- 测试 fixture：`quwoquan_service/services/chat-service/tests/support/contract_fixtures/scenarios/chat_scenarios.json`
- canonical：`quwoquan_service/services/realtime-gateway/contracts/realtime/connection/operations.yaml`
- canonical：`quwoquan_app/lib/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart`
- canonical：`quwoquan_app/lib/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart`
- canonical：[`app-cloud-business-object-commercial-closure`](../../../runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#req-004)
- canonical：`quwoquan_app/lib/cloud/services/realtime/remote_realtime_connection_delegate.dart`
- local_contract double：`quwoquan_app/test/support/fixtures/chat/fixture_realtime_connection_delegate.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 实时推送与离线同步（Realtime Push & Offline Sync）

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“实时推送与离线同步（Realtime Push & Offline Sync）”对应的公开行为。
- THEN 新成员事件生成系统消息并更新会话，退后台后 transport 释放，恢复前台后从服务端水位续接。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 断连期间的消息在重连后按游标补齐

- GIVEN 一侧断网，断网期间对端在同一会话连续发送多条消息。
- WHEN 断网侧恢复连接并收到传输恢复事件。
- THEN 端侧以本地最大 seq 为起点补齐缺口，最终序列无缺号、无重复且按 seq 有序。
- AND 补齐失败时返回 canonical failure 并保留游标，不静默截断时间线。

<a id="gwt-003"></a>
### GWT-003 群 fan-out 单点失败不影响其余接收方

- GIVEN 一个多成员群会话，其中一个接收方的分发通道不可用。
- WHEN 该群产生一条新消息。
- THEN 其余接收方仍然收到该消息。
- AND 失败接收方的分发失败被单独记录而不中断整批。

## 6. 依赖

- 前置要求：[`message-reliability-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 持久流、游标与传输恢复事件均未落地

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前会话事件只做即时广播且长轮询无游标，断连期间的消息永久丢失。恢复分支与补洞入口都存在但无人发出事件、无人调用，属于不可达代码。群分发为串行且首个失败即中断整批。
- 完成判定：`GWT-002` 与 `GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
