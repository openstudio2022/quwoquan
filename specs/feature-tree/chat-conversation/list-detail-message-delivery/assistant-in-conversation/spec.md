# L3 特性：assistant-in-conversation

## 功能说明
- 小趣以 `ConversationMember.memberType=assistant` 参与 direct/group 会话：可被邀入、被移除，@小趣 触发 AssistantMentioned 可靠事件。

## 约束
- chat-conversation 负责成员、消息、mentions 事实与事件发布；回复生成归 assistant-service，不在 chat 域内维护第二套助手逻辑。
- 个人助手全屏会话（AssistantConversation）与会话内 @小趣 共享助手 runtime，不得把个人助手会话伪装成 chat Conversation。
- 小趣成员被移除后，历史消息保留，新 mention 不再产生事件消费副作用。

## 验收标准
- A1：邀请小趣入会→@小趣→会话内收到小趣回复链路可用。
- A2：移除小趣成员后 mention 不再触发回复。
- A7：AssistantMentioned 事件流契约测试可复跑。
