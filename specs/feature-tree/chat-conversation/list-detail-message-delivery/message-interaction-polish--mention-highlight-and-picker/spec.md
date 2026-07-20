# L3 规格：message-interaction-polish--mention-highlight-and-picker

> **层级**：L3_story（隶属 L2 `list-detail-message-delivery`）
> **状态**：specified

## 0. 一句话定义

群成员在会话输入框键入 `@` 后，可从服务端权威成员名册中搜索并选择成员；发送、
未读提醒、气泡高亮和主页跳转共用 `Message.mentions`，群主/管理员另可使用
`__all__` 表达「@所有人」。

## 1. 用户价值

- 在活跃群聊中明确指向某个成员，降低消息被淹没的概率。
- 被提及者在消息首页获得独立 `mentionUnreadCount`，进入会话并标记已读后归零。
- 气泡中的提及可直接进入目标用户主页，形成沟通到关系主页的连续旅程。

## 2. 对象与真相源

| 数据 | 唯一真相源 | 消费者 |
|---|---|---|
| 可提及成员 | `ConversationMembershipReader/ListMembers` | 成员选择器 |
| 提及目标 | `Message.mentions`（稳定 `userId`；`__all__` 为保留值） | 消息存储、事件、App 气泡 |
| 提及显示名 | 发送文本中的 `@显示名` + 当前 roster 显示名；无法命中时按 mentions 顺序回退匹配文本 token | 输入态、气泡 |
| 提及未读 | `ConversationUserState.mentionUnreadCount` | Message Home / Inbox |
| 主页目标 | `Message.mentions.userId` | `AppRoutePaths.userProfile` |

`content` 只负责显示文本；权限、未读和点击目标不得通过解析字符串猜测。服务端必须
验证普通目标是当前活跃成员，客户端传入任意站外/非成员 ID 不得产生提醒。

## 3. 功能范围

### 3.1 输入与选择

1. 仅群会话在用户新输入 `@` 时打开贴底成员选择器；取消后保留原始 `@`。
2. 首屏最多显示 50 个候选，搜索经 `ListMembers(query)` 在服务端按
   `displayName/userId` 过滤，禁止仅搜索端侧已加载的 roster 子集。
3. 当前用户和 assistant 成员不进入普通成员候选；小趣继续走现有 `@小趣` 入口。
4. 选择成员后，用 `@显示名 ` 原子替换触发字符，并把稳定 `userId` 加入待发送 mentions。
5. 删除完整提及文本后，对应 ID 不得继续随消息发送。
6. 群主/管理员可选择「@所有人」；普通成员不可见该候选，服务端仍须二次鉴权。

### 3.2 发送与服务端约束

1. `mentions` 去空、按首次出现顺序去重，单条消息最多 50 个目标。
2. 普通目标必须是当前会话的活跃成员；`__all__` 仅允许群主/管理员使用。
3. 非群会话不接受成员提及；assistant 仅在该助手已加入会话时合法。
4. 校验后的 mentions 与 Message、MessageSent outbox、Sync/ListMessages 使用同一值。
5. `__all__` 使除发送者外的所有 user 成员 `mentionUnreadCount + 1`；普通提及只推进目标成员。
6. 幂等重放不得重复推进未读计数。

### 3.3 展示与跳转

1. 气泡只高亮 `Message.mentions` 对应的 `@...` token，不高亮普通文本中的孤立 `@`。
2. 普通成员提及可点击并进入对应用户主页；`__all__` 与 assistant 不跳用户主页。
3. 浅色/深色、自己/他人气泡均保持可读对比度；实现使用 `TextSpan`，禁止 HTML 替换。
4. 成员改名或离群后，若当前 roster 无显示名，按 mentions 与文本 token 的稳定顺序回退，
   仍保持点击 ID 正确。

## 4. 权限、隐私与失败语义

- 选择器与 `ListMembers` 只允许当前会话成员访问。
- 搜索日志只记录 query 是否为空、结果数和耗时，不记录搜索词、消息正文或显示名。
- 非成员目标、越权 `__all__`、超限或格式非法统一返回生成的
  `CHAT.USER.message_invalid`；不得暴露目标是否属于其他私密会话。
- roster/search 失败展示结构化可重试错误；消息草稿和已选择提及保留。

## 5. 非功能目标

- 选择器壳首帧即时出现，候选首批结果 P95 `< 200ms`。
- 单次候选结果 `<= 50`；服务端搜索使用转义后的字面量匹配，禁止正则注入。
- 高亮解析相对消息文本与 mentions 线性增长，不阻塞消息列表 60fps 滚动。
- 埋点至少覆盖 picker_open / search_result / member_selected / send_result /
  mention_clicked；不得携带 PII、正文或搜索词。

## 6. Out of Scope

- 跨会话或非成员提及。
- @提及专属系统 Push 通道（本 Story 只保证站内未读与实时消息主链）。
- 自定义群内昵称、mention 反向索引和运营群发。

## 7. 测试映射

- `local_contract`：输入触发、角色可见性、搜索/选择/删除、payload、气泡高亮与点击、
  Mock/Remote 参数一致。
- `api_integration`：成员搜索权限、非成员目标拒绝、`__all__` 角色矩阵、
  Message/MessageSent/Sync 一致、mentionUnreadCount 推进与已读归零。
- `user_acceptance`：双账号群聊中 A @ B，B 在消息首页看到提醒，进入会话看到高亮并
  点击到 B 的主页；普通成员无 @所有人。
