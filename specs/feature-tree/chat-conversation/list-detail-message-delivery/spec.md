# L2 Business Capability：消息列表与投递 (`list-detail-message-delivery`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

保证消息从发送、确认、重试到列表与详情展示的一致性

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“消息投递与列表 — 高并发大群消息有序投递”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。
- 消息时间线的本地落盘、历史游标分页、断连补洞、离线推送与会话性能预算，由 [`message-reliability-foundation`](../message-reliability-foundation/spec.md) 负责。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-012`](../../spec.md#scn-012)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：保证消息从发送、确认、重试到列表与详情展示的一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：保证消息从发送、确认、重试到列表与详情展示的一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：保证消息从发送、确认、重试到列表与详情展示的一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-018`](../../spec.md#scn-018)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：保证消息从发送、确认、重试到列表与详情展示的一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-020`](../../spec.md#scn-020)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：保证消息从发送、确认、重试到列表与详情展示的一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`assistant-in-conversation`](./assistant-in-conversation/spec.md)：小趣被移除后新 mention 不再发布事件；AssistantRemoved 生效。
- [`conversation-list-source-switch`](./conversation-list-source-switch/spec.md)：定义“会话列表来源切换”的可观察主路径、失败语义及父能力交接。
- [`delivery-and-read-receipt`](./delivery-and-read-receipt/spec.md)：定义“投递与读取回执”的可观察主路径、失败语义及父能力交接。
- [`message-interaction-polish`](./message-interaction-polish/spec.md)：**会话列表数据源**：ChatPage 混用 `ChatRepository` 和 `appContentRepository`，数据源不统一导致列表内容不一致。
- [`rich-media-message`](./rich-media-message/spec.md)：Office 文档优先调用系统可用应用打开；存在 canonical PDF 派生资源时使用统一预览器。
- [`voice-message`](./voice-message/spec.md)：完成录音、取消、上传、发送与播放，并防止页面退出或重复按下产生幽灵录音。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 list detail message delivery 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“保证消息从发送、确认、重试到列表与详情展示的一致性”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 Message.seq 由服务端 Redis INCR 原子生成，客户端禁止自行分配

- Message.seq 由服务端 Redis INCR 原子生成，客户端禁止自行分配
- 端侧消息列表必须按 seq 排序，禁止按 timestamp 排序

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 list detail message delivery 能力 SIT

- GIVEN 执行“list detail message delivery 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“list detail message delivery 能力”对应动作。
- THEN 直属 Story 共同交付“保证消息从发送、确认、重试到列表与详情展示的一致性”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 list detail message delivery 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：保证消息从发送、确认、重试到列表与详情展示的一致性。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 会话来源用三个交叠枚举加三个外键表达，非法组合无契约约束

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：存在语义交叠且缺少一致性不变量。`chat/conversation/fields.yaml` 用 `originType`（8 值）、`bindingType`（5 值）、`lifecyclePolicy`（5 值）三个枚举加 `circleId`/`circleGroupId`/`entityId` 三个外键共同表达"这个会话从哪来"，其中 `bindingType: circle_group` 与 `circleGroupId != null` 完全同义，`lifecyclePolicy: bound_to_circle` 与 `bindingType: circle` 完全同义，而 `object.yaml` 的 business_rules 对三者之间没有任何一致性不变量，导致 `bindingType: none` + `circleGroupId != null` 这类非法组合在契约层无法被拒绝。同一文件的 `status` 写了 `type: enum` 却没有 `enum_ref`，值域只存在于 description 文本里，而它是会话终态判定字段。另有 typed 语义泄漏：`message.type` 是 `MessageType` 枚举，但 `conversation.lastMessageType` 与 `chat_inbox_view.lastMessageType` 都是裸 string，而后者的注释明确说它驱动会话列表副标题图标，端侧要靠字符串匹配选图标。
- 完成判定：保留 `originType` 与外键，删除可推导的 `bindingType` 与 `lifecyclePolicy`（或在 business_rules 补齐三者对应表并由 local_contract 穷举非法组合断言拒绝）；`status` 补 `enum_ref`。两处 `lastMessageType` 改用 `MessageType`。`SIT-001` 的列表与详情一致性覆盖消息类型渲染。

<a id="open-003"></a>
### OPEN-003 conversation 概念在两个域同名，且 conversationId 跨域类型不一致

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：存在跨域命名歧义。`chat.conversation` 与 `assistant.assistant_conversation` 经核查是合理的不同概念而非概念冲突——前者是人际消息流的成员与序号容器（核心不变量是 seq 单调与成员治理），后者是 AI 编排上下文容器（核心不变量是"同一 conversation 最多一个 active run"），两者关系与字段零交集，且 chat 侧已明确把助手降级为 `memberType=assistant` 成员，说明概念切分本身做对了。但命名不够无歧义：两者在文档、日志与埋点里都被称作 conversation，且 `conversationId` 在 chat 域是 ObjectId、在 assistant 域是 string，跨域传参无编译期保护。
- 完成判定：assistant 侧改名为体现"一段连续交互 + 当前执行策略"的 session 语义（或退而统一 chat 侧对外类名为 ChatConversation），并明确 `conversationId` 仅指 chat 域；由 runtime-governance `OPEN-003` 的跨域同名字段类型一致门禁防回归。
