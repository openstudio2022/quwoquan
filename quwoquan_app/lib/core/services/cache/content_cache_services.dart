import 'dart:collection';

import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/object_cache_store.dart';

class PostObjectCacheService {
  PostObjectCacheService({
    ObjectCacheStore<ContentPostDetailPayload>? detailStore,
    ObjectCacheStore<PostBaseDto>? projectionStore,
  }) : _detailStore =
           detailStore ??
           ObjectCacheStore<ContentPostDetailPayload>(
             freshFor: const Duration(minutes: 30),
           ),
       _projectionStore =
           projectionStore ??
           ObjectCacheStore<PostBaseDto>(freshFor: const Duration(minutes: 10));

  final ObjectCacheStore<ContentPostDetailPayload> _detailStore;
  final ObjectCacheStore<PostBaseDto> _projectionStore;

  CacheReadResult<ContentPostDetailPayload>? getDetail(String postId) {
    return _detailStore.get(postId);
  }

  CacheReadResult<PostBaseDto>? getProjection(String postId) {
    return _projectionStore.get(postId);
  }

  void putDetail(ContentPostDetailPayload payload) {
    final post = payload.post;
    final version = _resolvePostVersion(post);
    _detailStore.put(
      post.id,
      payload,
      objectVersion: version,
      cacheClass: CacheClass.recent,
    );
    putProjection(post);
  }

  void putProjection(PostBaseDto post) {
    if (post.id.trim().isEmpty) {
      return;
    }
    _projectionStore.put(
      post.id,
      post,
      objectVersion: _resolvePostVersion(post),
      cacheClass: CacheClass.recent,
    );
  }

  void putProjections(Iterable<PostBaseDto> posts) {
    for (final post in posts) {
      putProjection(post);
    }
  }

  void removePost(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return;
    }
    _detailStore.remove(normalized);
    _projectionStore.remove(normalized);
  }

  int clearRecentDetails() {
    return _detailStore.clearAllRebuildable();
  }

  int clearAllRebuildable() {
    return _detailStore.clearAllRebuildable() +
        _projectionStore.clearAllRebuildable();
  }

  int get detailCount => _detailStore.diskCount;

  int get projectionCount => _projectionStore.diskCount;
}

class ContentQuerySnapshot {
  const ContentQuerySnapshot({
    required this.key,
    required this.items,
    required this.fetchedAt,
    this.nextCursor,
    this.feedRequestId,
    this.rankingVersion,
    this.reasonVersion,
  });

  final String key;
  final List<PostBaseDto> items;
  final String? nextCursor;
  final DateTime fetchedAt;

  /// 服务端权威下发的归因上下文（随 feed envelope 缓存，命中缓存时一并回放）。
  final String? feedRequestId;
  final String? rankingVersion;
  final String? reasonVersion;

  CursorPage<PostBaseDto> toCursorPage() {
    return CursorPage<PostBaseDto>(items: items, nextCursor: nextCursor);
  }

  DiscoveryFeedPage toDiscoveryFeedPage() {
    return DiscoveryFeedPage(
      items: items,
      nextCursor: nextCursor,
      feedRequestId: feedRequestId,
      rankingVersion: rankingVersion,
      reasonVersion: reasonVersion,
    );
  }
}

class ContentQuerySnapshotStore {
  ContentQuerySnapshotStore({
    this.maxEntries = 80,
    this.freshFor = const Duration(minutes: 5),
  });

  final int maxEntries;
  final Duration freshFor;
  final LinkedHashMap<String, ContentQuerySnapshot> _snapshots =
      LinkedHashMap<String, ContentQuerySnapshot>();

  CacheReadResult<ContentQuerySnapshot>? get(String key) {
    final normalized = key.trim();
    if (normalized.isEmpty) {
      return null;
    }
    final snapshot = _snapshots.remove(normalized);
    if (snapshot == null) {
      return null;
    }
    _snapshots[normalized] = snapshot;
    final freshness = DateTime.now().difference(snapshot.fetchedAt) <= freshFor
        ? CacheFreshness.fresh
        : CacheFreshness.stale;
    return CacheReadResult<ContentQuerySnapshot>(
      value: snapshot,
      source: CacheReadSource.disk,
      freshness: freshness,
      syncState: freshness == CacheFreshness.fresh
          ? CacheSyncState.idle
          : CacheSyncState.refreshing,
      cacheClass: CacheClass.recent,
      objectVersion: snapshot.fetchedAt.toUtc().toIso8601String(),
      diagnostics: const CacheDiagnostics(hitLayer: 'querySnapshot'),
    );
  }

  void put({
    required String key,
    required List<PostBaseDto> items,
    String? nextCursor,
    String? feedRequestId,
    String? rankingVersion,
    String? reasonVersion,
  }) {
    final normalized = key.trim();
    if (normalized.isEmpty) {
      return;
    }
    _snapshots.remove(normalized);
    _snapshots[normalized] = ContentQuerySnapshot(
      key: normalized,
      items: List<PostBaseDto>.unmodifiable(items),
      nextCursor: nextCursor,
      feedRequestId: feedRequestId,
      rankingVersion: rankingVersion,
      reasonVersion: reasonVersion,
      fetchedAt: DateTime.now(),
    );
    while (_snapshots.length > maxEntries) {
      _snapshots.remove(_snapshots.keys.first);
    }
  }

  int clearAll() {
    final count = _snapshots.length;
    _snapshots.clear();
    return count;
  }

  int invalidatePost(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return 0;
    }
    final keys = _snapshots.entries
        .where(
          (entry) => entry.value.items.any((item) => item.id == normalized),
        )
        .map((entry) => entry.key)
        .toList(growable: false);
    for (final key in keys) {
      _snapshots.remove(key);
    }
    return keys.length;
  }

  int get count => _snapshots.length;
}

String contentFeedQueryKey({
  required String category,
  String? identity,
  String? type,
  String? subCategory,
  String? cursor,
  required String sort,
  required int limit,
}) {
  final parts = <String>[
    'surface=discoveryFeed',
    'category=${category.trim()}',
    'identity=${(identity ?? '').trim()}',
    'type=${(type ?? '').trim()}',
    'subCategory=${(subCategory ?? '').trim()}',
    'cursor=${(cursor ?? '').trim()}',
    'sort=${sort.trim()}',
    'limit=$limit',
  ];
  return parts.join('&');
}

String _resolvePostVersion(PostBaseDto post) {
  final map = post.toMap();
  // 缓存版本以「最后变更时间」为准：updatedAt 优先，缺失回退不可变的 createdAt。
  // 不再用 publishedAt 借壳——发布时间不是内容变更时间。
  final version = (map['updatedAt'] ?? map['createdAt'])?.toString().trim();
  return version?.isNotEmpty == true ? version! : post.id;
}
