# chat-detail-avatar-display 设计方案

## 设计动因

对话页缺少用户头像展示（AppBar 无头像、消息气泡旁无头像），且每次进入会话都重新请求用户信息，缺少缓存机制。

## 上游输入评审

- `chat-detail-avatar-display/spec.md` 已冻结 AD1~AD7 功能
- `acceptance.yaml` 已定义 A1~A9 验收
- 用户信息缓存的时间戳驱动刷新协议已确认

## 方案对比

### 对比 1：缓存存储引擎

#### 方案 A：纯内存 Map

**优点**：最简
**缺点**：App 重启后丢失，冷启动需全量请求

#### 方案 B：内存 LRU + 磁盘 Hive（选定）

**优点**：热路径走内存（≤1ms），冷启动从磁盘恢复
**缺点**：需维护两层一致性

#### 方案 C：SQLite

**优点**：复杂查询
**缺点**：用户缓存场景不需要关系型查询

**选定方案 B**：两层缓存最佳平衡。

### 对比 2：刷新策略

#### 方案 A：TTL 过期刷新

**缺点**：无变化时也强制刷新，浪费流量

#### 方案 B：时间戳比对按需刷新（选定）

**优点**：有变化才拉取，无变化零流量
**缺点**：需要新增 `/users/timestamps` 接口

**选定方案 B**。

## 关键设计决策

### KD-1：UserProfileCacheService 两层架构

```dart
class UserProfileCacheService {
  final LruMap<String, UserProfileCacheEntry> _memory; // 200 条上限
  late Box<UserProfileCacheEntry> _disk;                // 永久保存
  
  /// 优先内存 → 磁盘 → null
  UserProfileCacheEntry? get(String userId);
  
  /// 写入内存 + 磁盘
  Future<void> put(UserProfileCacheEntry entry);
  
  /// 批量查本地时间戳
  Map<String, DateTime> getTimestamps(List<String> userIds);
}
```

### KD-2：UserProfileSyncService

```dart
class UserProfileSyncService {
  final UserRepository _userRepo;
  final UserProfileCacheService _cache;
  
  /// 冷却时间控制
  final Map<String, DateTime> _lastCheckTime = {};
  static const _cooldown = Duration(seconds: 30);
  
  /// 批量检查并刷新有变化的用户信息
  Future<void> refreshIfNeeded(List<String> userIds);
}
```

### KD-3：刷新流程

```
进入对话页:
1. 读缓存 → 立即渲染头像/名字（内存 → 磁盘 → 占位）
2. 检查冷却时间（30s 内不重复）
3. POST /users/timestamps → 批量查云端时间戳
4. 比对：cloud > local → 收集 staleIds
5. GET /users/profiles?ids=stale1,stale2 → 拉取变化用户
6. 更新两层缓存 → Provider 自动通知 UI 静默刷新
```

### KD-4：对话页 AppBar 头像

```dart
// 1v1 对话
AppBar(
  leading: BackButton,
  title: Row(
    children: [
      RoundedSquareAvatar(size: 36, imageUrl: otherUser.avatarUrl),
      SizedBox(width: AppSpacing.sm),
      Text(otherUser.displayName),
    ],
  ),
)

// 群聊
AppBar(
  title: Text(conversation.title),
)
```

### KD-5：消息气泡头像

在 `ChatMessageBubble` 中，非自己发送的消息旁显示 `RoundedSquareAvatar(size: 40)`，点击跳转用户主页。

### KD-6：新增云端接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `POST /users/timestamps` | POST | body: `{userIds: [...]}` → `{timestamps: {uid: ts}}` |
| `GET /users/profiles` | GET | `?ids=u1,u2` → 批量用户信息（已有/扩展） |

### KD-7：头像尺寸体系

| 场景 | 尺寸 | 用途 |
|---|---|---|
| 会话列表 | 56px | `_ConversationTile` |
| 消息气泡旁 | 40px | `ChatMessageBubble` |
| AppBar | 36px | 对话页标题栏 |
| 设置页成员 | 52px | `ChatSettingsPage._MemberAvatar` |

## TDD / ATDD 策略

| Task | 验收项 | 测试层 | Red 先行 |
|---|---|---|---|
| T1: UserProfileCacheService | A4~A5 | T2 | 单元测试 LRU + Hive |
| T2: UserProfileSyncService | A6~A7 | T2/T3 | 单元测试时间戳比对 + 冷却 |
| T3: AppBar 头像 | A1 | T2/T4 | Widget test |
| T4: 消息气泡头像 | A2~A3 | T2 | Widget test |
| T5: 设置页头像尺寸 | A9 | T2/T4 | Widget test |
| T6: 接口扩展 | A6 | T1 | 契约测试 |

## 未来演进

- 支持在线状态指示灯
- 头像加载动画（shimmer）
