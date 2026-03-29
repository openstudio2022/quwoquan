# group-member-roster-version-sync 设计方案

## 上游规格评审

| 输入 | 结论 |
|------|------|
| `spec.md`（本场景） | 已冻结展示名、`sort`、合并事件、revision、建群/更新事务边界 |
| `contracts/metadata/messages/conversation/` | 已增 `membersRosterRevision`、`ListMembers.sort`、`ConversationRosterUpdated` |
| `list-detail-message-delivery/realtime-push-and-offline-sync` | 端侧实时 handler 需订阅合并事件并定点刷新 |
| 既有 `MemberJoined` 实现 | 改为域内/审计或迁移期双发；客户端主路径切 `ConversationRosterUpdated` |

## 方案对比与选型

### 展示名来源

| 方案 | 说明 | 结论 |
|------|------|------|
| A | chat-service 写成员时同步 user-profile 快照到 `ConversationMember.displayName`/`avatarUrl` | **选定**（与 metadata 字段一致，端云同源，Mock 模拟同一规则） |
| B | 仅返回 `userId`，端侧 N+1 拉资料 | 拒绝：端云易分叉，违背「Mock 与云一致」 |

**并列名**：排序 `display_name_asc` 时第二键必须为 `userId`；UI 可在设计中选择是否展示次要标识（本 baseline 不强制 UI 副标题）。

### 加入顺序 `joined_asc`

- 存储：以 `ConversationMember.joinedAt` 升序为主序；**同一事务内批量创建**（建群初始成员）须赋予**严格单调**的 `joinedAt`（例如循环内递增 1ms）或引入显式 `joinSequence`（**本 baseline 优先递增 `joinedAt`**，避免新增字段；若 Mongo 精度不足再开 CR 增 `joinSequence`）。
- 与 `membersRosterRevision`：每次成员集合变化递增 revision，与 `updatedAt` 同事务写入。

### 推送合并

| 方案 | 说明 | 结论 |
|------|------|------|
| A | chat-service 在应用层 `time.AfterFunc` 防抖合并后发一条 `ConversationRosterUpdated` | **选定**（实现简单，窗口 50–100ms） |
| B | 仅依赖 realtime-gateway 合并 MemberJoined | 拒绝：网关缺少业务语义，难以合并群名变更 |

**合并窗口内**聚合 `aspects`（如 `members`、`title`、`rules`）；窗口结束发 **一条** 事件，payload 携带最新 `membersRosterRevision` 与 `updatedAt`。

### 拉取

- 客户端维护每会话 `lastKnownMembersRosterRevision`。
- `ConversationRosterUpdated` 或 `GetConversation` 发现 revision 变大 → **仅**拉取该会话的 `ListMembers`（带默认 `sort`）及必要设置。
- `ListConversationTimestamps` / 缓存行的 `updatedAt` 必须与 `Conversation.updatedAt` 对齐，以便离线同步发现「群资料/成员可能变了」。

## 云侧事务边界（重申）

1. **CreateConversation**：单事务 — `Conversation` 插入、`membersRosterRevision=1`（或从 0→1 规则在实现中固定）、`updatedAt=now`、群主 + 初始成员 + 各 `ConversationUserState`、计数。禁止「先插空群再异步加人」作为默认路径。
2. **并发更新**（AddMembers、RemoveMember、改群名、管理员等）：各请求**独立事务**；读当前 revision → 变更成员/设置 → `$inc membersRosterRevision` → 写 `updatedAt` → 提交 → 投递合并队列。
3. **其他成员**：不参与创建事务；仅通过 **推送（合并事件）** 与 **拉取（revision/时间戳）** 达到最终一致。

## metadata / codegen 基线

- `fields.yaml`：`Conversation.membersRosterRevision`
- `_shared/types.yaml`：`MemberListSort`
- `service.yaml`：`ListMembers` 增加 `sort` query
- `events.yaml`：`ConversationRosterUpdated`
- `make -C quwoquan_service verify-metadata` ✓
- `make codegen-app` ✓（Chat API 路径常量已生成）
- Go：`model.Conversation` / `event` 常量已与 metadata 对齐（chat 聚合完整 codegen 未纳入 `make codegen`，本次由 `/dev` 收敛到单一生成入口或延续 metadata-first 手同步直至 tooling 补齐）

## 观测与回滚

- 指标：`conversation_roster_merge_window_ms`、`ConversationRosterUpdated` 发布 QPS、revision 缺口补拉次数。
- 回滚：关闭合并窗口退化为「每笔变更即发事件」（feature flag），客户端仍可以 revision 拉取保持一致。

## T1~T4 证据矩阵

| ID | 描述 | T1 | T2 | T3 | T4 |
|----|------|----|----|----|-----|
| M1 | metadata 契约 | ✓ | | | |
| M2 | ListMembers sort 契约测试 | ✓ | | ✓ | |
| M3 | Mock 展示名与 revision | | ✓ | | |
| M4 | AddMembers 合并事件 + revision 单调 | | | ✓ | |
| M5 | 双客户端成员列表最终一致 | | | ✓ | ✓ |
