import 'dart:collection';

import 'package:flutter/foundation.dart';

/// 作品浏览器按 post 保存的局部状态窗口。
///
/// 窗口只保存轻量身份，不持有 Post、Widget、BuildContext 或媒体对象。调用方通过
/// [onEvicted] 同步清理页码、主题、hydration 与授权 URL 等派生状态。
final class WorksViewerPostStateWindow {
  WorksViewerPostStateWindow(
    this._onEvicted, {
    this.capacity = 16,
    this.protectedViewportRadius = 2,
  }) : assert(capacity > 0),
       assert(protectedViewportRadius >= 0),
       assert(protectedViewportRadius * 2 + 1 <= capacity);

  final int capacity;
  final int protectedViewportRadius;
  final void Function(String postId) _onEvicted;
  final LinkedHashSet<String> _residentPostIds = LinkedHashSet<String>();
  Set<String> _protectedPostIds = const <String>{};

  bool contains(String postId) => _residentPostIds.contains(postId.trim());

  /// 更新 viewport，并保护当前项及两侧声明半径内的可见邻居。
  ///
  /// 其余条目按访问顺序淘汰；因此连续前滑时保留最近回滑上下文，而不会让历史
  /// 作品状态随 feed 长度增长。
  void updateViewport({
    required int itemCount,
    required int currentIndex,
    required String Function(int index) postIdAt,
  }) {
    if (itemCount <= 0) {
      return;
    }
    final safeCurrent = currentIndex.clamp(0, itemCount - 1);
    final start = (safeCurrent - protectedViewportRadius).clamp(0, itemCount);
    final end = (safeCurrent + protectedViewportRadius + 1).clamp(0, itemCount);
    final nextProtected = <String>{};
    for (var index = start; index < end; index += 1) {
      final postId = postIdAt(index).trim();
      if (postId.isEmpty) {
        continue;
      }
      nextProtected.add(postId);
      _touch(postId);
    }
    final currentPostId = postIdAt(safeCurrent).trim();
    if (currentPostId.isNotEmpty) {
      _touch(currentPostId);
    }
    _protectedPostIds = Set<String>.unmodifiable(nextProtected);
    _trim();
  }

  /// 记录某个作品局部状态刚被使用或更新。
  void touch(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return;
    }
    _touch(normalized);
    _trim();
  }

  /// 内存压力下仅保留当前作品；被淘汰状态可从 canonical Post 重新派生。
  void handleMemoryPressure({String? currentPostId}) {
    final normalized = currentPostId?.trim() ?? '';
    _protectedPostIds = normalized.isEmpty
        ? const <String>{}
        : <String>{normalized};
    if (normalized.isNotEmpty) {
      _touch(normalized);
    }
    final evicted = _residentPostIds
        .where((postId) => postId != normalized)
        .toList(growable: false);
    for (final postId in evicted) {
      _evict(postId);
    }
  }

  void remove(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty || !_residentPostIds.contains(normalized)) {
      return;
    }
    _evict(normalized);
  }

  void _touch(String postId) {
    _residentPostIds.remove(postId);
    _residentPostIds.add(postId);
  }

  void _trim() {
    while (_residentPostIds.length > capacity) {
      String? victim;
      for (final postId in _residentPostIds) {
        if (!_protectedPostIds.contains(postId)) {
          victim = postId;
          break;
        }
      }
      if (victim == null) {
        return;
      }
      _evict(victim);
    }
  }

  void _evict(String postId) {
    _residentPostIds.remove(postId);
    _onEvicted(postId);
  }

  @visibleForTesting
  List<String> get residentPostIds =>
      List<String>.unmodifiable(_residentPostIds);
}

/// 作品浏览器派生投影使用的固定容量 LRU。
///
/// 值必须可由 canonical 输入重建；淘汰不得改变业务事实或用户操作结果。
final class WorksViewerLruCache<K, V extends Object> {
  WorksViewerLruCache({this.capacity = 48}) : assert(capacity > 0);

  final int capacity;
  final LinkedHashMap<K, V> _entries = LinkedHashMap<K, V>();

  V? read(K key) {
    final value = _entries.remove(key);
    if (value == null) {
      return null;
    }
    _entries[key] = value;
    return value;
  }

  void write(K key, V value) {
    _entries.remove(key);
    _entries[key] = value;
    while (_entries.length > capacity) {
      _entries.remove(_entries.keys.first);
    }
  }

  V? remove(K key) => _entries.remove(key);

  void clear() => _entries.clear();

  @visibleForTesting
  int get count => _entries.length;

  @visibleForTesting
  List<K> get keys => List<K>.unmodifiable(_entries.keys);
}

@immutable
final class WorksViewerOriginalImageAccess {
  const WorksViewerOriginalImageAccess({
    required this.url,
    required this.expiresAt,
  });

  final String url;
  final DateTime expiresAt;

  /// 预留短安全窗口，避免把即将过期的授权 URL 交给新的图片请求。
  bool isUsableAt(
    DateTime now, {
    Duration safetyWindow = const Duration(seconds: 5),
  }) {
    return expiresAt.toUtc().isAfter(now.toUtc().add(safetyWindow));
  }
}
