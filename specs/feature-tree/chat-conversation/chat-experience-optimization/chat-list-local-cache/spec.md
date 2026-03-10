# L3 规格：chat-list-local-cache — 会话列表本地缓存与时间戳驱动端云同步

> **层级**：L3_story（隶属 L2 `chat-experience-optimization`）
> **状态**：specified

## 0. 一句话定义

会话列表本地持久化缓存，基于云端生成的时间戳做增量同步，确保打开趣聊页无白屏、有变化才刷新、端云数据最终一致。

## 1. 背景与动机

当前 `_loadConversations()` 每次打开趣聊页都通过 `FutureBuilder` 从云端全量加载会话列表：

1. **白屏体验差**：网络慢时用户看到 loading 转圈，无法立即操作。
2. **流量浪费**：每次打开都全量拉取，即使没有任何变化。
3. **新建会话不同步**：本地新建的会话没有同步到云端保存的机制。
4. **无离线能力**：无网络时列表为空，无法查看历史会话。

## 2. 目标用户

- 趣聊日活用户（高频打开趣聊列表）
- 弱网/地铁等场景用户

## 3. 功能范围

### 3.1 In-Scope

| 编号 | 功能 | 说明 |
|---|---|---|
| LC1 | 会话列表本地持久化 | Hive Box 存储完整会话 JSON + 云端时间戳，无 TTL，永久保存 |
| LC2 | 打开列表时先渲染本地 | 本地缓存优先渲染，后台异步同步 |
| LC3 | 全量会话索引同步 | 后台请求 `GET /conversations/timestamps` 获取全量 convId + updatedAt |
| LC4 | 增量比对刷新 | 逐条比对：本地不存在 → 新增；cloud.updatedAt > local → 刷新；本地有云端无 → 已删除 |
| LC5 | 批量拉取变化会话 | `POST /conversations/batch` 一次拉取所有变化的完整会话 |
| LC6 | 本地新建会话同步 | 本地新建会话立即写入缓存并异步同步云端，成功后用云端返回数据覆盖 |
| LC7 | WebSocket 事件驱动更新 | 收到 `conv.updated` 事件时主动更新对应缓存条目 |
| LC8 | 无网络降级 | 无网络时静默使用本地数据，不显示错误 |

### 3.2 Out-of-Scope

- 会话内消息缓存（属于消息投递链路）
- 用户头像/昵称缓存（由 `chat-detail-avatar-display` 承担）
- 群管理相关数据同步（由 `chat-group-admin-govern` 承担）

## 4. 端云同步协议设计

### 4.1 打开趣聊列表

```
端侧                                      云端
  │                                         │
  │ 1. 同步：读本地 Hive → 渲染（≤50ms）      │
  │                                         │
  │ 2. 异步：GET /conversations/timestamps   │
  │ ────────────────────────────────────────→│
  │ ←─ { items: [{id, updatedAt}...],       │
  │      serverTime }                       │
  │                                         │
  │ 3. 本地逐条比对：                         │
  │    新增 / 变化 → 收集 ids                 │
  │    本地有云端无 → 标记删除                 │
  │                                         │
  │ 4. POST /conversations/batch            │
  │    body: { ids: [需要刷新的 convId] }     │
  │ ────────────────────────────────────────→│
  │ ←─ { items: [完整 ConversationDto...] }  │
  │                                         │
  │ 5. 更新本地缓存 → diff 刷新 UI            │
```

### 4.2 云端新增接口

| 接口 | 方法 | 说明 | 负载估算 |
|---|---|---|---|
| `/conversations/timestamps` | GET | 返回用户所有会话 ID + updatedAt + type | 500 会话 ≈ 30KB，gzip ≈ 5KB |
| `/conversations/batch` | POST | 批量拉取指定 ID 的完整会话 | body: `{ids: [...]}` 最多 50 个/次 |

### 4.3 为什么选择全量 ID+时间戳而非 `since` 增量

| 方案 | 优点 | 缺点 |
|---|---|---|
| `since={ts}` 增量 | 传输更少 | 无法发现"本地有但云端已不存在"的会话（退群/被踢）；端侧时钟偏移可能漏同步 |
| **全量 ID+时间戳** | 能发现新增、变更、删除三种情况；无时钟依赖 | 传输稍多，但 gzip 后 ≤5KB |

选择全量 ID+时间戳方案。

### 4.4 本地新建会话同步

```
1. 用户发起新建会话
2. 端侧立即：
   a. 生成临时 ID（client_conv_xxx）
   b. 写入本地 Hive 缓存
   c. UI 立即显示该会话
3. 异步调用 POST /conversations（创建）
4. 成功后：用云端返回的正式 ID + updatedAt 覆盖本地缓存
5. 失败后：保留本地条目，标记 syncStatus=pending，下次同步时重试
```

## 5. 端侧存储结构

```dart
// Hive Box: 'conversation_cache'
class ConversationCacheEntry {
  final String conversationId;
  final String type;                // direct / group
  final Map<String, dynamic> data;  // 完整会话 JSON
  final String cloudUpdatedAt;      // 云端时间戳 ISO8601
  final String syncStatus;          // synced / pending
  final DateTime localCachedAt;     // 本地写入时间
}
```

## 6. 对标

| 维度 | 微信 | 趣聊目标 |
|---|---|---|
| 列表缓存 | 本地 SQLite + 增量同步 | Hive Box + 时间戳增量同步 |
| 首屏渲染 | 本地优先，≤50ms | 本地优先，≤100ms |
| 离线能力 | 完整离线会话列表 | 完整离线会话列表 |

## 7. 业务约束

- 时间戳由云端生成和维护，端侧不生成时间戳用于比较
- 端侧只做"是否需要刷新"的判断，不尝试合并冲突
- 磁盘缓存无 TTL，永久保存
- 批量拉取 `POST /conversations/batch` 单次最多 50 个 ID
- WebSocket `conv.updated` 事件携带完整会话数据时直接写缓存

## 8. 减少云端冲击的措施

| 措施 | 说明 |
|---|---|
| `/conversations/timestamps` 极轻量 | 仅返回 ID+时间戳，MongoDB 走索引 |
| 批量接口 | 一次请求替代 N 次单会话请求 |
| WebSocket 主动推送 | 减少轮询需求 |
| 冷启动仅同步一次 | 非轮询，仅打开时触发 |

## 9. 本地优先原则

| 场景 | 本地有数据 | 网络 | 行为 |
|---|---|---|---|
| 打开列表 | 有 | 有网 | 渲染本地 → 后台同步 → 增量更新 |
| 打开列表 | 有 | 无网 | 渲染本地，静默失败 |
| 打开列表 | 无（首次） | 有网 | 骨架屏 → 全量加载 → 渲染 |
| 打开列表 | 无 | 无网 | 空状态 + "网络不可用" |
| 后台刷新失败 | 有 | 超时 | 静默忽略，本地继续有效 |
| 后台刷新成功 | 有 | 正常 | diff 更新，仅刷新变化部分 |

## 10. 非功能要求

- 冷启动本地缓存读取到首屏渲染 ≤100ms
- 后台同步请求不阻塞 UI 线程
- diff 刷新：仅更新变化条目，不重建整个列表

## 11. 验收重点

### T1
- `/conversations/timestamps` 响应结构契约
- `/conversations/batch` 请求响应结构契约

### T2
- 有本地缓存时打开列表无白屏，直接显示缓存数据
- 本地新建会话立即可见
- 云端有变化的会话被正确增量刷新
- 本地有但云端无的会话被标记删除

### T3
- 端侧 → 云端时间戳比对正确：仅拉取有变化的会话
- 新建会话成功同步到云端后用正式 ID 覆盖

### T4
- 弱网环境下先渲染本地，后台同步完成后静默更新
- 无网络时会话列表可正常浏览
