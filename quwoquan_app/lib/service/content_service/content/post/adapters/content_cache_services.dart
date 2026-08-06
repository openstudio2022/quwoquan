// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:quwoquan_app/service/content_service/content/post/domain/generated/content_post_snapshot_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/object_cache_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentFeedEmptyReason, ContentFeedOutcome, isCanonicalSha256Digest;
import 'package:shared_preferences/shared_preferences.dart';

part 'content_query_snapshot_persistence_codec.dart';

class PostObjectCacheService {
  PostObjectCacheService({
    ObjectCacheStore<ContentPostDetailPayload>? detailStore,
    ObjectCacheStore<ContentPostViewData>? projectionStore,
    int maxMemoryEntries = 200,
  }) : _detailStore =
           detailStore ??
           ObjectCacheStore<ContentPostDetailPayload>(
             maxMemoryEntries: maxMemoryEntries,
             freshFor: const Duration(minutes: 30),
           ),
       _projectionStore =
           projectionStore ??
           ObjectCacheStore<ContentPostViewData>(
             maxMemoryEntries: maxMemoryEntries,
             freshFor: const Duration(minutes: 10),
           );

  final ObjectCacheStore<ContentPostDetailPayload> _detailStore;
  final ObjectCacheStore<ContentPostViewData> _projectionStore;

  CacheReadResult<ContentPostDetailPayload>? getDetail(String postId) {
    return _detailStore.get(postId);
  }

  CacheReadResult<ContentPostViewData>? getProjection(String postId) {
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

  void putProjection(ContentPostViewData post) {
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

  void putProjections(Iterable<ContentPostViewData> posts) {
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

  int get detailCount => _detailStore.count;

  int get projectionCount => _projectionStore.count;
}

class ContentQuerySnapshot {
  ContentQuerySnapshot({
    required this.key,
    required this.items,
    required this.fetchedAt,
    this.nextCursor,
    this.previousCursor,
    this.paginationExpiresAt,
    this.paginationSessionId,
    this.feedRequestId,
    this.policyDigest,
    this.outcome = ContentFeedOutcome.content,
    this.emptyReason,
  }) {
    final digest = policyDigest;
    if (digest != null && !isCanonicalSha256Digest(digest)) {
      throw const FormatException(
        'policyDigest must be a canonical SHA-256 digest',
      );
    }
  }

  final String key;
  final List<ContentPostViewData> items;
  final String? nextCursor;
  final String? previousCursor;
  final DateTime? paginationExpiresAt;
  final String? paginationSessionId;
  final DateTime fetchedAt;

  /// 服务端权威下发的归因上下文（随 feed envelope 缓存，命中缓存时一并回放）。
  final String? feedRequestId;
  final String? policyDigest;
  final ContentFeedOutcome outcome;
  final ContentFeedEmptyReason? emptyReason;

  CursorPage<ContentPostViewData> toCursorPage() {
    return CursorPage<ContentPostViewData>(
      items: items,
      nextCursor: nextCursor,
    );
  }

  DiscoveryFeedPage toDiscoveryFeedPage({
    String? currentSessionId,
    DateTime? now,
  }) {
    final normalizedCurrentSession = currentSessionId?.trim() ?? '';
    final normalizedSnapshotSession = paginationSessionId?.trim() ?? '';
    final paginationIsUsable =
        normalizedCurrentSession.isNotEmpty &&
        normalizedSnapshotSession == normalizedCurrentSession &&
        paginationExpiresAt != null &&
        paginationExpiresAt!.isAfter((now ?? DateTime.now()).toUtc());
    return DiscoveryFeedPage(
      items: items,
      outcome: outcome,
      emptyReason: emptyReason,
      nextCursor: paginationIsUsable ? nextCursor : null,
      previousCursor: paginationIsUsable ? previousCursor : null,
      paginationExpiresAt: paginationIsUsable ? paginationExpiresAt : null,
      feedRequestId: feedRequestId,
      policyDigest: policyDigest,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'key': key,
      'items': items.map(_postSnapshotMap).toList(growable: false),
      'nextCursor': nextCursor,
      'previousCursor': previousCursor,
      'paginationExpiresAt': paginationExpiresAt?.toUtc().toIso8601String(),
      'paginationSessionId': paginationSessionId,
      'fetchedAt': fetchedAt.toUtc().toIso8601String(),
      'feedRequestId': feedRequestId,
      'policyDigest': policyDigest,
      'outcome': outcome.name,
      'emptyReason': _feedEmptyReasonToWire(emptyReason),
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
          .map(
            (item) => contentPostViewDataFromReadModelMap(
              _normalizePostSnapshotMap(item),
            ),
          )
          .toList(growable: false);
      final isDiscoveryFeed = _queryKeyParts(key)['surface'] == 'discoveryFeed';
      final outcome = isDiscoveryFeed
          ? _requiredSnapshotFeedOutcome(map['outcome'])
          : _optionalSnapshotFeedOutcome(map['outcome']);
      final emptyReason = _snapshotFeedEmptyReason(map['emptyReason']);
      if (isDiscoveryFeed) {
        final validEnvelope = items.isEmpty
            ? outcome == ContentFeedOutcome.empty && emptyReason != null
            : outcome == ContentFeedOutcome.content && emptyReason == null;
        if (!validEnvelope) {
          return null;
        }
      }
      return ContentQuerySnapshot(
        key: key,
        items: List<ContentPostViewData>.unmodifiable(items),
        fetchedAt: DateTime.parse(rawFetchedAt).toLocal(),
        nextCursor: map['nextCursor']?.toString(),
        previousCursor: map['previousCursor']?.toString(),
        paginationExpiresAt: _optionalSnapshotDateTime(
          map['paginationExpiresAt'],
        ),
        paginationSessionId: map['paginationSessionId']?.toString(),
        feedRequestId: map['feedRequestId']?.toString(),
        policyDigest: _optionalSnapshotPolicyDigest(map['policyDigest']),
        outcome: outcome,
        emptyReason: emptyReason,
      );
    } catch (_) {
      return null;
    }
  }
}

String? _optionalSnapshotPolicyDigest(Object? value) {
  if (value == null) {
    return null;
  }
  if (value is! String || !isCanonicalSha256Digest(value)) {
    throw const FormatException(
      'policyDigest must be a canonical SHA-256 digest',
    );
  }
  return value;
}

ContentFeedOutcome _requiredSnapshotFeedOutcome(Object? value) {
  return switch (value) {
    'content' => ContentFeedOutcome.content,
    'empty' => ContentFeedOutcome.empty,
    _ => throw const FormatException('feed snapshot outcome is invalid'),
  };
}

ContentFeedOutcome _optionalSnapshotFeedOutcome(Object? value) => value == null
    ? ContentFeedOutcome.content
    : _requiredSnapshotFeedOutcome(value);

ContentFeedEmptyReason? _snapshotFeedEmptyReason(Object? value) {
  return switch (value) {
    'no_active_release' => ContentFeedEmptyReason.noActiveRelease,
    'no_eligible_content' => ContentFeedEmptyReason.noEligibleContent,
    'following_empty' => ContentFeedEmptyReason.followingEmpty,
    'continuation_end' => ContentFeedEmptyReason.continuationEnd,
    null => null,
    _ => throw const FormatException('feed snapshot emptyReason is invalid'),
  };
}

String? _feedEmptyReasonToWire(ContentFeedEmptyReason? reason) {
  return switch (reason) {
    ContentFeedEmptyReason.noActiveRelease => 'no_active_release',
    ContentFeedEmptyReason.noEligibleContent => 'no_eligible_content',
    ContentFeedEmptyReason.followingEmpty => 'following_empty',
    ContentFeedEmptyReason.continuationEnd => 'continuation_end',
    null => null,
  };
}

DateTime? _optionalSnapshotDateTime(Object? value) {
  final raw = value?.toString().trim() ?? '';
  return raw.isEmpty ? null : DateTime.parse(raw).toUtc();
}

class ContentQuerySnapshotPersistencePolicy {
  const ContentQuerySnapshotPersistencePolicy({
    this.maxItemsPerSnapshot = 30,
    this.maxUserPostSubjects = 20,
    this.maxFeedPagesPerQuery = 4,
    this.maxPersistedBytes = defaultMaxPersistedBytes,
  });

  static const int defaultMaxPersistedBytes = 2 * 1024 * 1024;

  final int maxItemsPerSnapshot;
  final int maxUserPostSubjects;
  final int maxFeedPagesPerQuery;
  final int maxPersistedBytes;

  List<ContentQuerySnapshot> selectPersistableSnapshots(
    Iterable<ContentQuerySnapshot> snapshots,
  ) {
    return selectPersistableSnapshotChains(
      snapshots,
    ).expand((chain) => chain).toList(growable: false);
  }

  List<List<ContentQuerySnapshot>> selectPersistableSnapshotChains(
    Iterable<ContentQuerySnapshot> snapshots,
  ) {
    final materialized = snapshots
        .where(
          (snapshot) =>
              _isPersistableSurface(snapshot.key) &&
              snapshot.items.length <= maxItemsPerSnapshot,
        )
        .toList(growable: false);
    final allowedUserSubjects = _latestUserPostSubjects(materialized);
    final firstByBase = <String, ContentQuerySnapshot>{};
    final latestByBase = <String, ContentQuerySnapshot>{};
    for (final snapshot in materialized) {
      if (!_isAllowedUserPostSubject(snapshot.key, allowedUserSubjects)) {
        continue;
      }
      if (_queryKeyParts(snapshot.key)['surface'] == 'discoveryFeed') {
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

    final chains = <List<ContentQuerySnapshot>>[
      ..._contiguousFeedWindowChains(materialized),
    ];
    final selectedOtherSurfaces = <String, ContentQuerySnapshot>{};
    for (final snapshot in firstByBase.values) {
      selectedOtherSurfaces[snapshot.key] = snapshot;
    }
    for (final snapshot in latestByBase.values) {
      selectedOtherSurfaces[snapshot.key] = snapshot;
    }
    for (final snapshot in selectedOtherSurfaces.values) {
      chains.add(<ContentQuerySnapshot>[snapshot]);
    }
    return chains;
  }

  List<List<ContentQuerySnapshot>> _contiguousFeedWindowChains(
    List<ContentQuerySnapshot> snapshots,
  ) {
    if (maxFeedPagesPerQuery <= 0) {
      return const <List<ContentQuerySnapshot>>[];
    }
    final pagesByBase = <String, Map<String, ContentQuerySnapshot>>{};
    for (final snapshot in snapshots) {
      final parts = _queryKeyParts(snapshot.key);
      if (parts['surface'] != 'discoveryFeed') {
        continue;
      }
      final base = _baseSignatureForKey(snapshot.key);
      final cursor = (parts['cursor'] ?? '').trim();
      pagesByBase.putIfAbsent(
        base,
        () => <String, ContentQuerySnapshot>{},
      )[cursor] = snapshot;
    }
    final chains = <List<ContentQuerySnapshot>>[];
    for (final pagesByCursor in pagesByBase.values) {
      var cursor = '';
      final visitedCursors = <String>{};
      final chain = <ContentQuerySnapshot>[];
      for (
        var pageIndex = 0;
        pageIndex < maxFeedPagesPerQuery;
        pageIndex += 1
      ) {
        if (!visitedCursors.add(cursor)) {
          break;
        }
        final page = pagesByCursor[cursor];
        if (page == null) {
          break;
        }
        chain.add(page);
        final nextCursor = page.nextCursor?.trim() ?? '';
        if (nextCursor.isEmpty) {
          break;
        }
        cursor = nextCursor;
      }
      if (chain.isNotEmpty) {
        chains.add(chain);
      }
    }
    chains.sort((a, b) => b.first.fetchedAt.compareTo(a.first.fetchedAt));
    return chains;
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

abstract interface class ContentQuerySnapshotPersistenceBackend {
  Future<String?> read(String storageKey);

  Future<void> write(String storageKey, String payload);

  Future<void> remove(String storageKey);
}

class SharedPreferencesContentQuerySnapshotPersistenceBackend
    implements ContentQuerySnapshotPersistenceBackend {
  const SharedPreferencesContentQuerySnapshotPersistenceBackend();

  @override
  Future<String?> read(String storageKey) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(storageKey);
  }

  @override
  Future<void> write(String storageKey, String payload) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(storageKey, payload);
  }

  @override
  Future<void> remove(String storageKey) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(storageKey);
  }
}

class ContentQuerySnapshotStore {
  ContentQuerySnapshotStore({
    this.maxEntries = 80,
    this.freshFor = const Duration(minutes: 5),
    this.maximumAge = const Duration(hours: 24),
    bool persistToPreferences = false,
    String storageKey = defaultStorageKey,
    ContentQuerySnapshotPersistencePolicy persistencePolicy =
        const ContentQuerySnapshotPersistencePolicy(),
    ContentQuerySnapshotPersistenceBackend persistenceBackend =
        const SharedPreferencesContentQuerySnapshotPersistenceBackend(),
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
    DateTime Function()? now,
  }) : _persistToPreferences = persistToPreferences,
       _storageKey = storageKey,
       _persistencePolicy = persistencePolicy,
       _persistenceBackend = persistenceBackend,
       _telemetrySink = telemetrySink,
       _now = now ?? DateTime.now {
    if (maxEntries <= 0) {
      throw ArgumentError.value(maxEntries, 'maxEntries', 'must be positive');
    }
    if (freshFor <= Duration.zero) {
      throw ArgumentError.value(freshFor, 'freshFor', 'must be positive');
    }
    if (maximumAge < freshFor) {
      throw ArgumentError.value(
        maximumAge,
        'maximumAge',
        'must be greater than or equal to freshFor',
      );
    }
    _hydration = _persistToPreferences
        ? _hydrateFromPreferences()
        : Future<void>.value();
  }

  static const String defaultStorageKey = 'qwq.content_query_snapshots';

  final int maxEntries;
  final Duration freshFor;
  final Duration maximumAge;
  final bool _persistToPreferences;
  final String _storageKey;
  final ContentQuerySnapshotPersistencePolicy _persistencePolicy;
  final ContentQuerySnapshotPersistenceBackend _persistenceBackend;
  final CacheTelemetrySink _telemetrySink;
  final DateTime Function() _now;
  final LinkedHashMap<String, ContentQuerySnapshot> _snapshots =
      LinkedHashMap<String, ContentQuerySnapshot>();
  final Set<String> _diskBackedKeys = <String>{};
  late final Future<void> _hydration;
  Future<void>? _persistenceDrain;
  bool _persistenceDirty = false;

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
    final age = _snapshotAge(snapshot);
    if (age > maximumAge) {
      _diskBackedKeys.remove(normalized);
      _schedulePersist();
      _telemetrySink.record('query_snapshot.expire', <String, Object?>{
        'count': 1,
        'source': 'read',
      });
      return null;
    }
    _snapshots[normalized] = snapshot;
    final freshness = age <= freshFor
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
    required List<ContentPostViewData> items,
    String? nextCursor,
    String? previousCursor,
    DateTime? paginationExpiresAt,
    String? paginationSessionId,
    String? feedRequestId,
    String? policyDigest,
    ContentFeedOutcome outcome = ContentFeedOutcome.content,
    ContentFeedEmptyReason? emptyReason,
  }) {
    final normalized = key.trim();
    if (normalized.isEmpty) {
      return;
    }
    if (_queryKeyParts(normalized)['surface'] == 'discoveryFeed') {
      final validEnvelope = items.isEmpty
          ? outcome == ContentFeedOutcome.empty && emptyReason != null
          : outcome == ContentFeedOutcome.content && emptyReason == null;
      if (!validEnvelope) {
        throw const FormatException(
          'feed snapshot requires a canonical outcome envelope',
        );
      }
    }
    _snapshots.remove(normalized);
    _snapshots[normalized] = ContentQuerySnapshot(
      key: normalized,
      items: List<ContentPostViewData>.unmodifiable(items),
      nextCursor: nextCursor,
      previousCursor: previousCursor,
      paginationExpiresAt: paginationExpiresAt,
      paginationSessionId: paginationSessionId,
      feedRequestId: feedRequestId,
      policyDigest: policyDigest,
      outcome: outcome,
      emptyReason: emptyReason,
      fetchedAt: _now(),
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
    while (true) {
      final drain = _persistenceDrain;
      if (drain == null) {
        return;
      }
      await drain;
    }
  }

  Future<void> _hydrateFromPreferences() async {
    try {
      final raw = await _persistenceBackend.read(_storageKey);
      if (raw == null || raw.isEmpty) {
        return;
      }
      if (_utf8WireLength(
            raw,
            stopAfter: _persistencePolicy.maxPersistedBytes,
          ) >
          _persistencePolicy.maxPersistedBytes) {
        await _persistenceBackend.remove(_storageKey);
        return;
      }
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        return;
      }
      final rawSnapshots = decoded['snapshots'];
      if (rawSnapshots is! List) {
        return;
      }
      final decodedSnapshots = <ContentQuerySnapshot>[];
      var expiredCount = 0;
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
        if (_snapshotAge(snapshot) > maximumAge) {
          expiredCount += 1;
          continue;
        }
        decodedSnapshots.add(snapshot);
      }
      final persistableSnapshots = _persistencePolicy
          .selectPersistableSnapshots(decodedSnapshots);
      var restoredCount = 0;
      for (final snapshot in persistableSnapshots) {
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
      if (expiredCount > 0) {
        _telemetrySink.record('query_snapshot.expire', <String, Object?>{
          'count': expiredCount,
          'source': 'restore',
        });
        _schedulePersist();
      }
    } catch (_) {
      return;
    }
  }

  Duration _snapshotAge(ContentQuerySnapshot snapshot) {
    final age = _now().difference(snapshot.fetchedAt);
    return age.isNegative ? Duration.zero : age;
  }

  void _schedulePersist() {
    if (!_persistToPreferences) {
      return;
    }
    _persistenceDirty = true;
    _persistenceDrain ??= _drainPersistence();
    unawaited(_persistenceDrain);
  }

  Future<void> _drainPersistence() async {
    try {
      while (_persistenceDirty) {
        _persistenceDirty = false;
        await _persistToPreferencesStore();
      }
    } finally {
      _persistenceDrain = null;
    }
  }

  Future<void> _persistToPreferencesStore() async {
    try {
      if (_snapshots.isEmpty) {
        await _persistenceBackend.remove(_storageKey);
        return;
      }
      final snapshotChains = _persistencePolicy.selectPersistableSnapshotChains(
        _snapshots.values,
      );
      final payload = _encodePersistableSnapshotPayload(
        snapshotChains: snapshotChains,
        maxPersistedBytes: _persistencePolicy.maxPersistedBytes,
      );
      if (payload == null) {
        await _persistenceBackend.remove(_storageKey);
        return;
      }
      await _persistenceBackend.write(_storageKey, payload);
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
  String? channelId,
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
    'channelId=${(channelId ?? '').trim()}',
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

String _resolvePostVersion(ContentPostViewData post) {
  // 缓存版本只消费 canonical updatedAt；缺失时使用对象主键。
  // 不再用 publishedAt 借壳——发布时间不是内容变更时间。
  final version = post.updatedAt?.toUtc().toIso8601String().trim();
  return version?.isNotEmpty == true ? version! : post.id;
}

Map<String, dynamic> _postSnapshotMap(ContentPostViewData post) {
  return Map<String, dynamic>.from(
    contentPostProjectionFromViewData(post).toWire(),
  );
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
