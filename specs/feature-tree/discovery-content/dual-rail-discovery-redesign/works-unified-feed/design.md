# works-unified-feed 设计

## 设计动因

当前三路独立 feed 导致：①端侧需维护三份 cursor state；②无法做跨类型交替呈现；③三类内容在同一垂直流中时顺序由端侧拼接，体验碎片化。将混排职责上移到服务端是唯一可控方案。

## 适用场景与约束

**适用**：内容量和用户量尚小，服务端初期可用规则排序（时间 + 类型交替），后续无缝接入推荐信号。
**约束**：filter_type 切换必须重置 cursor（不能跨类型接续分页）；服务端必须保证同一 cursor 值不会跨 filter_type 复用。

## 关键决策

### 1. API 设计

```
GET /v1/content/works-feed
  query:
    filter_type: string?  # null / "image" / "video" / "article"
    cursor:      string?  # 上次响应的 next_cursor
    limit:       int      # 默认 20
  response:
    items:      List<PostBaseDto>  # 多态，包含 type 字段
    next_cursor: string?           # 无更多时为 null
```

### 2. 端侧 Repository 扩展

```dart
// ContentRepository 新增方法
Future<CursorPage<PostBaseDto>> listWorksFeedPage({
  String? filterType,   // null | 'image' | 'video' | 'article'
  int limit = 20,
  String? cursor,
});
```

### 3. WorksFeedProvider

```dart
// lib/ui/discovery/providers/works_feed_provider.dart
@riverpod
class WorksFeedNotifier extends _$WorksFeedNotifier {
  Future<void> load({String? filterType});
  Future<void> appendNextPage();
}
```

- `filterType` 变更 → 重置 `cursor`，清空 `items`，重新 `load`
- 与现有 `discoveryFeedMapProvider` 并存，旧 provider 在微趣轨和过渡期继续使用

### 4. 服务端初期排序策略（规则）

- `filter_type=null`：每 3 条中至少包含 1 类（image/video/article），按创建时间倒序
- `filter_type=X`：仅返回该类型，按创建时间倒序
- 后续：接入 `feed-orchestration-recommendation/personalized-ranking` 信号

## 备选方案对比

| 方案 | 描述 | 选用原因 |
|------|------|----------|
| **A（选定）服务端混排** | 新端点，服务端控制顺序 | 端侧逻辑简单，排序灵活可演进 |
| B 端侧三路归并 | 分别请求三类 feed，端侧按时间插入 | cursor 管理极复杂，分页不均匀，废弃 |

## 未来演进

- 接入推荐排序（依赖 `personalized-ranking` 完成）
- A/B 实验参数透传（`experiment_id` query param 扩展）
