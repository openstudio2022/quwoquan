# L3 Scenario: persona-context-propagation

## 节点定位

- `L1_capability`: `user-identity-profile-relationship`
- `L2_journey`: `persona-follow-graph`
- `L3_scenario`: `persona-context-propagation`

本场景冻结“当前激活分身如何成为全链路默认动作主体”的合同。它不是新的身份实体，而是 user 域 `active persona` 对 content/chat/circle/assistant/invite/notification 的统一透传规则。

## 背景与动机

当前仓库里已经出现了多种分身引用字段：

- 评论：`personaId`
- 聊天消息：`senderPersonaId`
- 邀请：`subAccountId`
- 公开主页：`profileSubjectId / subAccountId`

但这些字段目前更像“预埋能力”，还没有冻结一版完整产品合同：

1. 激活分身后，哪些下游必须无条件切换，哪些允许显式覆盖，还没有统一规则。
2. 若下游拿不到 persona 上下文，当前系统更容易静默退回到 owner 或默认用户，存在串号风险。
3. 助手链路内部还有 `stack.persona` 等提示词概念，若不明确边界，容易把“用户分身”与“助手人格”混为一谈。

本场景的目标是冻结分身透传的主语法：谁提供 active persona、谁消费它、丢失时如何阻断与恢复。

## 目标用户

- 会在不同分身之间切换并立即发帖、评论、聊天或进入圈子的用户。
- 希望小趣回答和工具调用理解当前创作/社交身份的用户。
- 需要排查串号、身份错绑、通知错投递问题的测试与运维团队。

## 功能范围

### F1. active persona 作为跨域唯一默认主体

- user 域提供当前 `active persona` 真相源。
- 所有需要“谁在行动”的链路，默认都从 active persona 取主体。
- 只有在产品明确提供“临时改用另一个分身”的交互时，才允许显式覆盖默认主体。

### F2. content 域透传

第一版必须覆盖：

- 发帖
- 评论
- 个人主页互动回跳后的作者识别

规则：

- 发帖与评论默认使用 active persona。
- 若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- 内容对象需保留不可变作者快照，避免停用后记录显示异常。

### F3. chat / circle / invite 域透传

第一版必须覆盖：

- 聊天消息发送者
- 圈子加入、创建、圈内展示
- 邀请归因与关系扩散

规则：

- 聊天消息的发送主体使用 `senderPersonaId` 或等价字段。
- 圈子相关写入必须明确落到具体分身，而不是 owner。
- 邀请和增长归因默认归属于发起动作时的 active persona。

### F4. assistant / notification 域透传

助手与通知必须消费当前分身上下文，但不得复制身份模型：

- 助手读取 active persona 的 `profileSubjectId`、可见资料和权限边界。
- 助手的 prompt 层 `stack.persona` 只代表语气与角色，不代表用户分身实体。
- 通知渲染与跳转回放需带上正确的分身主体，避免把 A 分身的通知打开到 B 分身上下文。

### F5. 串号阻断与恢复

如果下游在关键动作中拿不到 persona 上下文，系统必须阻断或提示恢复，不允许静默回退：

- 阻断提交并提示重新确认当前分身
- 回退到最近一次稳定 active persona 快照
- 记录 mismatch 事件，供灰度与回滚判断

### F6. 观测与灰度

透传链路至少要观察：

- active persona switch latency
- attribution mismatch
- stale persona context
- notification open under wrong persona
- assistant session persona drift

## 领域划分

| 域 | 负责 | 禁止 |
|---|---|---|
| `user` | 提供 active persona 真相源、切换与上下文基线 | 在 UI 外把 owner 暴露给动作链路 |
| `content` | 消费当前 persona 做创作/评论归属与记录快照 | 自建分身主实体 |
| `chat` | 消费当前 persona 做 sender 归属与记录快照 | 以 owner 作为默认发送主体 |
| `circle` | 消费当前 persona 做加入/创建/圈内展示归属 | 把圈子成员关系挂到 owner |
| `assistant` | 读取当前 persona 作为上下文 | 把提示词 persona 当成用户分身实体 |
| `notification` | 保证打开通知时恢复正确 persona 上下文 | 忽略 persona 上下文直接进入默认用户态 |

## 权限边界与数据生命周期

- 只有 owner 能切换 active persona；下游域只消费切换结果。
- 下游写入对象必须保存足够的作者快照，避免 persona 停用后记录渲染丢失。
- 下游域可以持久化 `personaId / subAccountId / profileSubjectId`，但不得反查或暴露 owner 映射。
- 助手会话与通知回放至少要带上 active persona 上下文，不得默认落回 owner。

## 不做什么（Out of Scope）

- 分身管理台 UI。
- 公开资料读写合同。
- 粉丝/关注图谱分页与关系写入细节。
- 助手 prompt、skill、tool 本身的产品重构。

## 对标输入

| 对标 | 吸收点 |
|---|---|
| 微信 | 切换身份后的会话与关系主体必须稳定 |
| 小红书 | 评论与内容创作必须感知作者身份 |
| 微博 | 公开互动与运营主体的一致性 |

## 非功能目标

- active persona 切换后，下游关键动作主体一致生效 P95 < 1s。
- 灰度期 `attribution mismatch` 目标为 `0` 个 P0 事故。
- 通知与助手回放的 persona drift 事件必须可观测、可回滚。

## 验收重点

1. active persona 成为 content/chat/circle/assistant/invite/notification 的唯一默认主体来源。
2. 下游丢失 persona 上下文时，系统阻断或提示恢复，而不是静默回退到 owner。
3. 助手明确只消费用户分身上下文，不自建第二套 persona 实体。
