/// Provider 级短时缓存（TTL）基础设施。
///
/// 背景：`autoDispose` Provider 在最后一个监听者移除时立即销毁，导致 tab 切换、
/// 路由 push/pop、长列表回收等「同一会话内的瞬时取消订阅—再订阅」反复重打服务
/// （见 backlog R-ID09 验收项④）。
///
/// 设计取舍：不采用 `keepAlive()` + `Timer` 的保活配方——`Timer` 在
/// `testWidgets` 的 FakeAsync 下会成为「pending timer」使用例外部 `ProviderContainer`
/// 的测试失败。改为容器作用域的纯内存 TTL 缓存：autoDispose Provider 仍照常销毁，
/// 但在重建时先查缓存命中即复用，未命中或过期才取数。缓存随 `ProviderContainer`
/// 释放而回收，无定时器、测试可重复、不跨用例泄漏。
library;

/// 单条带时间戳的缓存值。
class TtlCacheEntry<T> {
  TtlCacheEntry(this.value, this.storedAt);

  final T value;
  final DateTime storedAt;

  bool isFresh(Duration ttl) => DateTime.now().difference(storedAt) < ttl;
}

/// 按字符串 key 索引的短时缓存（容器作用域，由持有它的 Provider 生命周期托管）。
class TtlCache<T> {
  final Map<String, TtlCacheEntry<T>> _entries = <String, TtlCacheEntry<T>>{};

  /// 命中且未过期返回缓存值条目，否则返回 null（顺带清理过期项）。
  TtlCacheEntry<T>? readFresh(String key, Duration ttl) {
    final entry = _entries[key];
    if (entry == null) {
      return null;
    }
    if (!entry.isFresh(ttl)) {
      _entries.remove(key);
      return null;
    }
    return entry;
  }

  void write(String key, T value) {
    _entries[key] = TtlCacheEntry<T>(value, DateTime.now());
  }
}
