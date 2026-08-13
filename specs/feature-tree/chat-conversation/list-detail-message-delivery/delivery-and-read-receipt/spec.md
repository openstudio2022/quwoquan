# L3 Story：投递与读取回执 (`delivery-and-read-receipt`)

> 所属能力：[`list-detail-message-delivery`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望消息发送、送达与已读状态按同一顺序推进，重放不会重复计数，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “投递与读取回执”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 投递与读取回执

- “投递与读取回执”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 投递与读取回执

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“投递与读取回执”对应的公开行为。
- THEN 通过父能力公开契约交付“投递与读取回执”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`list-detail-message-delivery`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 投递与读取回执 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺进入会话时对端历史已读态的读面。当前 peer 读位仅由
  `ConversationReadWatermarkAdvanced` 实时事件推进，冷进入会话时自己的历史消息
  在对端再次已读前显示单勾，需契约演进补对端水位查询。尚缺群聊逐人已读的
  production Remote UAT。1v1 双勾真链已落地：App 消费对端水位事件单调推进
  `peerReadSeq`（读者为自己时只收敛多设备未读、不伪造对端已读），自己消息按
  `seq <= peerReadSeq` 判定双勾（`isRead` 硬编码已移除），证据见
  `chat_read_watermark_receipt__local_contract_test.dart`。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
