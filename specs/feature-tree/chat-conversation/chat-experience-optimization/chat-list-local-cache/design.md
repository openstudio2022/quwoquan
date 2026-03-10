# chat-list-local-cache 设计方案

## 设计动因

当前趣聊列表每次打开都 `FutureBuilder` 全量请求云端，无缓存、白屏、无离线能力。需要实现本地优先+时间戳驱动的增量同步。

## 上游输入评审

- `chat-list-local-cache/spec.md` 已冻结 LC1~LC8 功能
- `acceptance.yaml` 已定义 A1~A9 验收
- 端云同步协议已在 explore 阶段与产品确认

## 方案对比

### 对比 1：本地存储引擎

#### 方案 A：SharedPreferences

**优点**：无额外依赖
**缺点**：不适合存储大量结构化数据，序列化/反序列化性能差

#### 方案 B：Hive（选定）

**优点**：高性能 key-value NoSQL，支持 TypeAdapter，Flutter 生态成熟
**缺点**：需要注册 TypeAdapter

#### 方案 C：SQLite (sqflite/drift)

**优点**：关系型查询强
**缺点**：会话列表场景不需要复杂查询，引入过重

**选定方案 B**：Hive Box 存储会话缓存，性能优良且 API 简洁。

### 对比 2：同步策略

#### 方案 A：`since={timestamp}` 增量

**优点**：传输少
**缺点**：无法发现已删除的会话（退群/被踢），时钟偏移风险

#### 方案 B：全量 ID+时间戳索引（选定）

**优点**：能发现新增、变更、删除三种情况；无时钟依赖
**缺点**：传输稍多（但 500 会话 gzip 后仅 5KB）

**选定方案 B**：全量索引方案更健壮。

### 对比 3：变化会话拉取

#### 方案 A：逐个 `GET /conversations/{id}`

**缺点**：N 个变化 = N 次请求

#### 方案 B：`POST /conversations/batch`（选定）

**优点**：一次请求拉取所有变化会话

**选定方案 B**。

### 对比 4：消息时间展示策略

#### 方案 A：直接展示 UTC 偏移

**优点**：简单
**缺点**：用户看到的时间与系统时钟不一致，跨时区用户困惑

#### 方案 B：云端存储 UTC+8，端侧转本地时区（选定）

**优点**：云端统一存储北京时间（UTC+8），端侧按设备时区自动转换，跨时区用户看到当地时间
**缺点**：需引入时区转换工具函数

**选定方案 B**。

### 对比 5：时间戳分拆策略（应对群聊高频消息）

#### 方案 A：单一 `updatedAt`

**缺点**：群聊每条消息都更新 updatedAt，导致时间戳同步时活跃群"永远有变化"，缓存命中率低

#### 方案 B：分拆 `settingsUpdatedAt` + `lastMessageAt`（选定）

**优点**：消息频率变化不触发会话元数据拉取；列表排序/预览仅需轻量字段
**缺点**：需修改索引接口返回结构

**选定方案 B**。

## 关键设计决策

### KD-1：ConversationCacheService

```dart
class ConversationCacheService {
  late Box<ConversationCacheEntry> _box;
  
  Future<void> init();
  List<ConversationCacheEntry> getAll();
  ConversationCacheEntry? get(String convId);
  Future<void> put(ConversationCacheEntry entry);
  Future<void> putAll(List<ConversationCacheEntry> entries);
  Future<void> remove(String convId);
}
```

### KD-2：ConversationSyncService

```dart
class ConversationSyncService {
  final ChatRepository _repo;
  final ConversationCacheService _cache;
  
  /// 后台同步：全量索引 → 比对 → 批量拉取变化
  Future<SyncResult> syncFromCloud();
}

class SyncResult {
  final int added;
  final int updated;
  final int removed;
}
```

### KD-3：同步流程

```
1. 读本地缓存 → 立即渲染（StateNotifier emit）
2. 后台调用 syncFromCloud()
   a. GET /conversations/timestamps → 全量索引
   b. 逐条比对 convId + settingsUpdatedAt + lastMessageAt
   c. settingsUpdatedAt 变化 → 需批量拉取完整会话数据（成员、设置等）
   d. lastMessageAt 变化但 settingsUpdatedAt 未变 → 仅更新列表展示字段
      （lastMessagePreview / lastMessageAt / unreadCount 直接从索引取）
   e. 收集本地有云端无的 ids → 标记删除
   f. POST /conversations/batch 仅拉取 settingsUpdatedAt 变化的会话
   g. 更新本地缓存
3. StateNotifier diff emit → UI 增量刷新
```

### KD-4：Riverpod Provider 结构

```dart
// 会话列表 StateNotifier
final conversationListProvider = 
    StateNotifierProvider<ConversationListNotifier, ConversationListState>((ref) {
  final cache = ref.watch(conversationCacheServiceProvider);
  final sync = ref.watch(conversationSyncServiceProvider);
  return ConversationListNotifier(cache, sync);
});
```

### KD-5：新建会话本地优先

```
1. 生成临时 ID (client_conv_xxx)
2. 写入 Hive，syncStatus=pending
3. UI 立即显示
4. 异步 POST /conversations
5. 成功 → 用云端 ID/updatedAt 覆盖，syncStatus=synced
6. 失败 → 保留 pending，下次同步重试
```

### KD-6：新增云端接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `GET /conversations/timestamps` | GET | 返回用户所有会话 `{id, settingsUpdatedAt, lastMessageAt, lastMessagePreview, unreadCount, type}` |
| `POST /conversations/batch` | POST | body: `{ids: [...]}` → 返回完整会话列表（成员、设置等） |

`ChatRepository` abstract 新增两个方法，Mock 和 Remote 同步实现。

### KD-7：消息时间全链路设计

#### 云端存储规范

所有时间字段统一存储为 **ISO 8601 UTC+08:00（北京时间）** 格式：

```
2026-03-10T18:35:22+08:00
```

| 字段 | 生成方 | 格式 | 说明 |
|---|---|---|---|
| `message.timestamp` | 云端 | ISO 8601 UTC+08:00 | 消息的权威时间，以云端收到时间为准 |
| `conversation.lastMessageAt` | 云端 | ISO 8601 UTC+08:00 | 最后一条消息的云端时间 |
| `conversation.settingsUpdatedAt` | 云端 | ISO 8601 UTC+08:00 | 群设置/成员变更时间 |
| `user.profileUpdatedAt` | 云端 | ISO 8601 UTC+08:00 | 用户资料变更时间 |

**核心约束**：端侧不产生任何业务时间戳，所有时间以云端为唯一真相源。

#### 端侧时间转换与展示

```dart
/// 将云端 UTC+8 时间转换为设备本地时区展示
///
/// 规则：
/// 1. 解析云端 ISO 8601 字符串（含 +08:00 偏移）
/// 2. 转换为设备本地时区（DateTime.toLocal()）
/// 3. 如果设备未设置时区或无法获取 → 直接展示云端原始时间（北京时间）
/// 4. 展示格式统一为 "{日期标签} 上午/下午H:mm"
class ChatTimeFormatter {
  /// 统一时间格式："{日期标签} 上午/下午H:mm"
  ///
  /// 日期标签规则：
  /// - 今天 → "今天"
  /// - 昨天 → "昨天"
  /// - 本周（2~6天前）→ "周X"
  /// - 同年 → "MM/dd"（两位月两位日，如 03/10）
  /// - 跨年 → "yy/MM/dd"（两位年，如 26/01/09）
  static String format(DateTime serverTime) {
    final local = serverTime.toLocal();
    final dayLabel = _dayLabel(local);
    final timeLabel = _timeLabel(local);
    return '$dayLabel $timeLabel';
  }

  /// 仅日期标签（用于列表等紧凑场景可选）
  static String formatDateOnly(DateTime serverTime) {
    return _dayLabel(serverTime.toLocal());
  }

  /// 仅时间部分（上午/下午H:mm）
  static String formatTimeOnly(DateTime serverTime) {
    return _timeLabel(serverTime.toLocal());
  }

  static String _dayLabel(DateTime local) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final msgDay = DateTime(local.year, local.month, local.day);
    final diff = today.difference(msgDay).inDays;

    if (diff == 0) return '今天';
    if (diff == 1) return '昨天';
    if (diff >= 2 && diff <= 6) {
      const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
      return weekdays[local.weekday - 1];
    }
    final mm = local.month.toString().padLeft(2, '0');
    final dd = local.day.toString().padLeft(2, '0');
    if (local.year != now.year) {
      final yy = (local.year % 100).toString().padLeft(2, '0');
      return '$yy/$mm/$dd';
    }
    return '$mm/$dd';
  }

  static String _timeLabel(DateTime local) {
    final h = local.hour;
    final m = local.minute.toString().padLeft(2, '0');
    if (h == 0) return '上午12:$m';
    if (h < 12) return '上午$h:$m';
    if (h == 12) return '下午12:$m';
    return '下午${h - 12}:$m';
  }

  /// 从 ISO 8601 字符串解析，失败时返回 null（不回退到本地时钟）
  static DateTime? tryParseServerTime(String? iso) {
    if (iso == null || iso.isEmpty) return null;
    return DateTime.tryParse(iso);
  }
}
```

#### 消息发送的乐观更新时间处理

```
发送方时间流转：
  ① 乐观插入：timestamp = null（展示"发送中"状态，不显示时间）
  ② 云端确认：timestamp = resp.timestamp（云端 UTC+8 时间）
  ③ UI 展示：ChatTimeFormatter.formatBubbleTime(timestamp.toLocal())

接收方时间流转：
  ① WS 推送：timestamp = payload['timestamp']（云端 UTC+8）
  ② UI 展示：ChatTimeFormatter.formatBubbleTime(timestamp.toLocal())

异常处理：
  - timestamp 解析失败 → 不显示时间（显示空字符串），不回退到 DateTime.now()
  - 设备时区无法获取 → DateTime.toLocal() 回退到 UTC，即展示云端原始时间
```

#### 聊天列表 + 气泡时间展示

统一格式：`{日期标签} 上午/下午H:mm`

```
数据来源：conversation['lastMessageAt'] 或 message.timestamp（云端 UTC+8）
展示逻辑：ChatTimeFormatter.format(serverTime)

示例（云端时间 2026-03-10T18:35:22+08:00，北京用户）：
  - 今天     → "今天 下午6:35"
  - 昨天     → "昨天 下午6:35"
  - 本周三   → "周三 下午6:35"
  - 同年     → "03/10 下午6:35"
  - 跨年     → "25/12/31 下午6:35"

跨时区示例（同一条消息）：
  - 北京用户（UTC+8）→ "今天 下午6:35"
  - 纽约用户（UTC-4）→ "今天 上午6:35"
  - 伦敦用户（UTC+0）→ "今天 上午10:35"
```

### KD-8：时间戳分拆与同步优化

#### 群聊高频消息场景分析

200 人活跃群，每分钟 50+ 条消息时：
- `lastMessageAt` 每条消息变化 → 高频
- `settingsUpdatedAt` 仅群名/成员/设置变更 → 低频

如果不分拆，每次同步都判定该群"有变化"，触发全量 batchGetConversations。

#### 分拆后索引接口返回结构

```json
{
  "items": [
    {
      "id": "conv_123",
      "settingsUpdatedAt": "2026-03-09T14:00:00+08:00",
      "lastMessageAt": "2026-03-10T18:35:22+08:00",
      "lastMessagePreview": "好的，明天见",
      "unreadCount": 15,
      "type": "group"
    }
  ]
}
```

#### 端侧分拆比对逻辑

```
对每个会话：
  1. settingsUpdatedAt 变化 → 加入 needFetchIds（需批量拉取完整数据）
  2. lastMessageAt 变化但 settingsUpdatedAt 未变
     → 仅用索引中的 lastMessagePreview / lastMessageAt / unreadCount 更新本地缓存
     → 不加入 needFetchIds，不触发 batchGetConversations
  3. 两者都未变 → 跳过
```

### KD-9：同步防抖

```dart
class ConversationSyncService {
  DateTime? _lastSyncTime;
  static const _minSyncInterval = Duration(seconds: 30);

  Future<bool> sync() async {
    if (_syncing) return false;
    if (_lastSyncTime != null &&
        DateTime.now().difference(_lastSyncTime!) < _minSyncInterval) {
      return false;
    }
    _lastSyncTime = DateTime.now();
    // ... 同步逻辑
  }
}
```

用户反复切 Tab 时，30 秒内只同步一次。

### KD-10：WS 事件驱动列表实时更新

用户在对话 A 中时，对话 B 收到新消息应实时更新列表缓存，不等退出后同步。

```
RealtimeMessageHandler 新增处理：

  case 'MessageSent':
    ① chatMessageProvider 追加消息（已有）
    ② conversationCache 更新 lastMessagePreview / lastMessageAt / unreadCount

  case 'ConversationSettingsUpdated':
    ① 刷新 conversationCache 中该会话的设置数据
    ② 如果用户正在该会话的设置页 → 触发 UI 刷新

  case 'MemberJoined' / 'MemberLeft':
    ① 插入系统消息到 chatMessageProvider
    ② 更新 conversationCache 中的成员计数
```

### KD-11：WS 断连后 seq gap 补全

用户在会话中停留时 WS 可能断连重连，需自动补全缺失消息：

```
RealtimeConnectionManager 重连成功后：
  → 广播 'ReconnectComplete' 事件
  → ChatMessageNotifier 监听到重连 → syncFromSeq(localMaxSeq)
  → ConversationSyncService 监听到重连 → sync()（受防抖保护）
```

## TDD / ATDD 策略

| Task | 验收项 | 测试层 | Red 先行 |
|---|---|---|---|
| T1: ConversationCacheService | A9 | T2 | 单元测试 Hive CRUD |
| T2: ConversationSyncService（含分拆比对） | A2~A5 | T2/T3 | 单元测试比对逻辑 |
| T3: StateNotifier 本地优先 | A1 | T2 | Widget test 无白屏 |
| T4: 新建会话同步 | A6 | T2/T3 | 单元测试 |
| T5: ChatRepository 接口扩展 | A2~A3 | T1 | 契约测试 |
| T6: WS 事件驱动列表更新 | A8 | T2/T3 | 单元测试 |
| T7: 无网络降级 | A7 | T2/T4 | Widget test |
| T8: ChatTimeFormatter 时区转换 | — | T2 | 单元测试多时区场景 |
| T9: 同步防抖 | — | T2 | 单元测试间隔控制 |
| T10: WS 重连 seq gap 补全 | — | T2/T3 | 单元测试重连→补全 |

## 未来演进

- 磁盘容量过大时后台静默清理最久未访问的条目
- 支持消息级增量同步（当前仅会话级）
- 国际化时间格式（"上午/下午"→ AM/PM，"昨天"→ Yesterday 等）
