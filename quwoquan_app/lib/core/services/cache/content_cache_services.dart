// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/object_cache_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

class PostObjectCacheService {
  PostObjectCacheService({
    ObjectCacheStore<ContentPostDetailPayload>? detailStore,
    ObjectCacheStore<PostBaseDto>? projectionStore,
    int maxMemoryEntries = 200,
  }) : _detailStore =
           detailStore ??
           ObjectCacheStore<ContentPostDetailPayload>(
             maxMemoryEntries: maxMemoryEntries,
             freshFor: const Duration(minutes: 30),
           ),
       _projectionStore =
           projectionStore ??
           ObjectCacheStore<PostBaseDto>(
             maxMemoryEntries: maxMemoryEntries,
             freshFor: const Duration(minutes: 10),
           );

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

  Map<String, dynamic> toMap({int? maxItems}) {
    final snapshotItems = maxItems == null ? items : items.take(maxItems);
    return <String, dynamic>{
      'key': key,
      'items': snapshotItems.map(_postSnapshotMap).toList(growable: false),
      'nextCursor': nextCursor,
      'fetchedAt': fetchedAt.toUtc().toIso8601String(),
      'feedRequestId': feedRequestId,
      'rankingVersion': rankingVersion,
      'reasonVersion': reasonVersion,
    };
  }

  static ContentQuerySnapshot? fromMap(Map<String, dynamic> map) {
    try {
      final key = map['key']?.toString().trim() ?? '';
      final rawItems = map['items'];
      final rawFetchedAt = map['fetchedAt']?.toString() ?? '';
      if (key.isEmpty || rawItems is! List || rawFetchedAt.isEmpty) {
        return null;
      }
      final items = rawItems
          .whereType<Map>()
          .map((item) => postBaseDtoFromMap(_normalizePostSnapshotMap(item)))
          .toList(growable: false);
      return ContentQuerySnapshot(
        key: key,
        items: List<PostBaseDto>.unmodifiable(items),
        fetchedAt: DateTime.parse(rawFetchedAt).toLocal(),
        nextCursor: map['nextCursor']?.toString(),
        feedRequestId: map['feedRequestId']?.toString(),
        rankingVersion: map['rankingVersion']?.toString(),
        reasonVersion: map['reasonVersion']?.toString(),
      );
    } catch (_) {
      return null;
    }
  }
}

class ContentQuerySnapshotPersistencePolicy {
  const ContentQuerySnapshotPersistencePolicy({
    this.maxItemsPerSnapshot = 30,
    this.maxUserPostSubjects = 20,
  });

  final int maxItemsPerSnapshot;
  final int maxUserPostSubjects;

  List<ContentQuerySnapshot> selectPersistableSnapshots(
    Iterable<ContentQuerySnapshot> snapshots,
  ) {
    final materialized = snapshots
        .where((snapshot) => _isPersistableSurface(snapshot.key))
        .toList(growable: false);
    final allowedUserSubjects = _latestUserPostSubjects(materialized);
    final firstByBase = <String, ContentQuerySnapshot>{};
    final latestByBase = <String, ContentQuerySnapshot>{};
    for (final snapshot in materialized) {
      if (!_isAllowedUserPostSubject(snapshot.key, allowedUserSubjects)) {
        continue;
      }
      final baseSignature = _baseSignatureForKey(snapshot.key);
      if (_isFirstPageKey(snapshot.key)) {
        firstByBase.putIfAbsent(baseSignature, () => snapshot);
      }
      final previous = latestByBase[baseSignature];
      if (previous == null || snapshot.fetchedAt.isAfter(previous.fetchedAt)) {
        latestByBase[baseSignature] = snapshot;
      }
    }

    final selected = <String, ContentQuerySnapshot>{};
    for (final snapshot in firstByBase.values) {
      selected[snapshot.key] = snapshot;
    }
    for (final snapshot in latestByBase.values) {
      selected[snapshot.key] = snapshot;
    }
    return selected.values.toList(growable: false);
  }

  bool _isAllowedUserPostSubject(String key, Set<String> allowedSubjects) {
    final parts = _queryKeyParts(key);
    if (parts['surface'] != 'userPosts') {
      return true;
    }
    return allowedSubjects.contains((parts['userId'] ?? '').trim());
  }

  Set<String> _latestUserPostSubjects(List<ContentQuerySnapshot> snapshots) {
    final latestBySubject = <String, DateTime>{};
    for (final snapshot in snapshots) {
      final parts = _queryKeyParts(snapshot.key);
      if (parts['surface'] != 'userPosts') {
        continue;
      }
      final userId = (parts['userId'] ?? '').trim();
      if (userId.isEmpty) {
        continue;
      }
      final previous = latestBySubject[userId];
      if (previous == null || snapshot.fetchedAt.isAfter(previous)) {
        latestBySubject[userId] = snapshot.fetchedAt;
      }
    }
    final orderedSubjects = latestBySubject.entries.toList(growable: false)
      ..sort((a, b) => b.value.compareTo(a.value));
    return orderedSubjects
        .take(maxUserPostSubjects)
        .map((entry) => entry.key)
        .toSet();
  }

  bool _isPersistableSurface(String key) {
    final surface = _queryKeyParts(key)['surface'];
    return surface == 'discoveryFeed' || surface == 'userPosts';
  }

  bool _isFirstPageKey(String key) {
    return (_queryKeyParts(key)['cursor'] ?? '').trim().isEmpty;
  }

  String _baseSignatureForKey(String key) {
    final parts = key
        .split('&')
        .where((part) => !part.startsWith('cursor='))
        .toList(growable: false);
    return parts.join('&');
  }
}

class ContentQuerySnapshotStore {
  ContentQuerySnapshotStore({
    this.maxEntries = 80,
    this.freshFor = const Duration(minutes: 5),
    bool persistToPreferences = false,
    String storageKey = defaultStorageKey,
    ContentQuerySnapshotPersistencePolicy persistencePolicy =
        const ContentQuerySnapshotPersistencePolicy(),
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
  }) : _persistToPreferences = persistToPreferences,
       _storageKey = storageKey,
       _persistencePolicy = persistencePolicy,
       _telemetrySink = telemetrySink {
    _hydration = _persistToPreferences
        ? _hydrateFromPreferences()
        : Future<void>.value();
  }

  static const String defaultStorageKey = 'qwq.content_query_snapshots.v2';
  static const int _storageVersion = 2;

  final int maxEntries;
  final Duration freshFor;
  final bool _persistToPreferences;
  final String _storageKey;
  final ContentQuerySnapshotPersistencePolicy _persistencePolicy;
  final CacheTelemetrySink _telemetrySink;
  final LinkedHashMap<String, ContentQuerySnapshot> _snapshots =
      LinkedHashMap<String, ContentQuerySnapshot>();
  final Set<String> _diskBackedKeys = <String>{};
  late final Future<void> _hydration;
  Future<void>? _pendingPersist;

  Future<void> ensureHydrated() {
    return _hydration;
  }

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
    final source = _diskBackedKeys.contains(normalized)
        ? CacheReadSource.disk
        : CacheReadSource.memory;
    return CacheReadResult<ContentQuerySnapshot>(
      value: snapshot,
      source: source,
      freshness: freshness,
      syncState: freshness == CacheFreshness.fresh
          ? CacheSyncState.idle
          : CacheSyncState.refreshing,
      cacheClass: CacheClass.recent,
      objectVersion: snapshot.fetchedAt.toUtc().toIso8601String(),
      diagnostics: CacheDiagnostics(hitLayer: 'querySnapshot.${source.name}'),
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
    _diskBackedKeys.remove(normalized);
    while (_snapshots.length > maxEntries) {
      final evicted = _snapshots.keys.first;
      _snapshots.remove(evicted);
      _diskBackedKeys.remove(evicted);
    }
    _schedulePersist();
  }

  int clearAll() {
    final count = _snapshots.length;
    _snapshots.clear();
    _diskBackedKeys.clear();
    _schedulePersist();
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
      _diskBackedKeys.remove(key);
    }
    if (keys.isNotEmpty) {
      _schedulePersist();
    }
    return keys.length;
  }

  int get count => _snapshots.length;

  Future<void> flushPersistence() async {
    final pending = _pendingPersist;
    if (pending != null) {
      await pending;
    }
  }

  Future<void> _hydrateFromPreferences() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_storageKey);
      if (raw == null || raw.isEmpty) {
        return;
      }
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      if (decoded['version'] != _storageVersion) {
        return;
      }
      final rawSnapshots = decoded['snapshots'];
      if (rawSnapshots is! List) {
        return;
      }
      var restoredCount = 0;
      for (final rawSnapshot in rawSnapshots) {
        if (rawSnapshot is! Map) {
          continue;
        }
        final snapshot = ContentQuerySnapshot.fromMap(
          Map<String, dynamic>.from(rawSnapshot),
        );
        if (snapshot == null) {
          continue;
        }
        _snapshots.remove(snapshot.key);
        _snapshots[snapshot.key] = snapshot;
        _diskBackedKeys.add(snapshot.key);
        restoredCount += 1;
      }
      while (_snapshots.length > maxEntries) {
        final evicted = _snapshots.keys.first;
        _snapshots.remove(evicted);
        _diskBackedKeys.remove(evicted);
      }
      if (restoredCount > 0) {
        _telemetrySink.record('query_snapshot.restore', <String, Object?>{
          'count': restoredCount,
          'storageKey': _storageKey,
        });
      }
    } catch (_) {
      return;
    }
  }

  void _schedulePersist() {
    if (!_persistToPreferences) {
      return;
    }
    _pendingPersist = _persistToPreferencesStore();
    unawaited(_pendingPersist);
  }

  Future<void> _persistToPreferencesStore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final snapshots = _persistencePolicy.selectPersistableSnapshots(
        _snapshots.values,
      );
      final payload = <String, dynamic>{
        'version': _storageVersion,
        'snapshots': snapshots
            .map(
              (snapshot) => snapshot.toMap(
                maxItems: _persistencePolicy.maxItemsPerSnapshot,
              ),
            )
            .toList(growable: false),
      };
      await prefs.setString(_storageKey, jsonEncode(payload));
    } catch (_) {
      return;
    }
  }
}

Map<String, String> _queryKeyParts(String key) {
  final parts = <String, String>{};
  for (final segment in key.split('&')) {
    final separatorIndex = segment.indexOf('=');
    if (separatorIndex < 0) {
      parts[segment] = '';
      continue;
    }
    parts[segment.substring(0, separatorIndex)] = segment.substring(
      separatorIndex + 1,
    );
  }
  return parts;
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

String contentUserPostsQueryKey({
  required String userId,
  String? identity,
  String? type,
  String? visibility,
  String? cursor,
  required int limit,
}) {
  final parts = <String>[
    'surface=userPosts',
    'userId=${userId.trim()}',
    'identity=${(identity ?? '').trim()}',
    'type=${(type ?? '').trim()}',
    'visibility=${(visibility ?? '').trim()}',
    'cursor=${(cursor ?? '').trim()}',
    'limit=$limit',
  ];
  return parts.join('&');
}

String _resolvePostVersion(PostBaseDto post) {
  final map = post.toMap();
  // 缓存版本只消费 canonical updatedAt；缺失时使用对象主键。
  // 不再用 publishedAt 借壳——发布时间不是内容变更时间。
  final version = map['updatedAt']?.toString().trim();
  return version?.isNotEmpty == true ? version! : post.id;
}

Map<String, dynamic> _jsonSafeMap(Map<String, dynamic> map) {
  return map.map((key, value) => MapEntry(key, _jsonSafeValue(value)));
}

Map<String, dynamic> _postSnapshotMap(PostBaseDto post) {
  final map = _jsonSafeMap(post.toMap());
  map['postId'] = post.id;
  map['contentType'] = post.type;
  map['contentIdentity'] = post.identity;
  return map;
}

Map<String, dynamic> _normalizePostSnapshotMap(Map<dynamic, dynamic> raw) {
  final map = Map<String, dynamic>.from(raw);
  final postId = map['postId'];
  if (postId != null) {
    map['postId'] = postId.toString();
  }
  final contentType = map['contentType'];
  if (contentType != null) {
    map['contentType'] = contentType.toString();
  }
  final identity = map['contentIdentity'];
  if (identity != null) {
    map['contentIdentity'] = identity.toString();
  }
  return map;
}

Object? _jsonSafeValue(Object? value) {
  if (value is DateTime) {
    return value.toUtc().toIso8601String();
  }
  if (value is Map) {
    return value.map(
      (key, nestedValue) =>
          MapEntry(key.toString(), _jsonSafeValue(nestedValue)),
    );
  }
  if (value is Iterable) {
    return value.map(_jsonSafeValue).toList(growable: false);
  }
  return value;
}
