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
   b. 逐条比对 convId + updatedAt
   c. 收集新增/变化的 ids
   d. 收集本地有云端无的 ids → 标记删除
   e. POST /conversations/batch 批量拉取
   f. 更新本地缓存
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
| `GET /conversations/timestamps` | GET | 返回用户所有会话 `{id, updatedAt, type}` |
| `POST /conversations/batch` | POST | body: `{ids: [...]}` → 返回完整会话列表 |

`ChatRepository` abstract 新增两个方法，Mock 和 Remote 同步实现。

## TDD / ATDD 策略

| Task | 验收项 | 测试层 | Red 先行 |
|---|---|---|---|
| T1: ConversationCacheService | A9 | T2 | 单元测试 Hive CRUD |
| T2: ConversationSyncService | A2~A5 | T2/T3 | 单元测试比对逻辑 |
| T3: StateNotifier 本地优先 | A1 | T2 | Widget test 无白屏 |
| T4: 新建会话同步 | A6 | T2/T3 | 单元测试 |
| T5: ChatRepository 接口扩展 | A2~A3 | T1 | 契约测试 |
| T6: WS 事件驱动 | A8 | T2/T3 | 单元测试 |
| T7: 无网络降级 | A7 | T2/T4 | Widget test |

## 未来演进

- 磁盘容量过大时后台静默清理最久未访问的条目
- 支持消息级增量同步（当前仅会话级）
