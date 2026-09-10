// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import 'package:quwoquan_app/service/content_service/content/post/domain/generated/content_post_snapshot_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/object_cache_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ContentFeedEmptyReason,
        ContentFeedOutcome,
        FeedObjectCard,
        CloudOperationCancelledException,
        isCanonicalSha256Digest;
import 'package:shared_preferences/shared_preferences.dart';

part 'content_query_snapshot_persistence_codec.dart';

/// 这里只判定失败类别；调用方仍须证明同 scope/public/本地策略与年龄。
bool isContentCacheTransportFallback(Object error, {DateTime? deadlineAt}) {
  if ((deadlineAt != null && !DateTime.now().isBefore(deadlineAt)) ||
      error is CloudOperationCancelledException ||
      error is http.RequestAbortedException) {
    return false;
  }
  final failure = error is CloudException
      ? error
      : CloudErrorMapper.fromException(error);
  final kind = failure.runtimeFailure.kind;
  if (kind == RuntimeFailureKind.cancelled ||
      kind == RuntimeFailureKind.contract ||
      kind == RuntimeFailureKind.parsing ||
      failure.statusCode == 401 ||
      failure.statusCode == 403) {
    return false;
  }
  final status = failure.statusCode;
  if (status != null) return status == 429 || (status >= 500 && status <= 599);
  return kind == RuntimeFailureKind.network ||
      kind == RuntimeFailureKind.timeout;
}

class PostObjectCacheService {
  PostObjectCacheService({
    ObjectCacheStore<ContentPostDetailPayload>? detailStore,
    ObjectCacheStore<ContentPostViewData>? projectionStore,
    int maxMemoryEntries = 200,
    this.detailsMaxAge = const Duration(hours: 24),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now,
       _detailStore =
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
           ) {
    if (detailsMaxAge <= Duration.zero ||
        detailsMaxAge > const Duration(hours: 24)) {
      throw ArgumentError.value(detailsMaxAge, 'detailsMaxAge');
    }
  }

  final ObjectCacheStore<ContentPostDetailPayload> _detailStore;
  final ObjectCacheStore<ContentPostViewData> _projectionStore;
  String _namespace = '';
  final Duration detailsMaxAge;
  final DateTime Function() _now;
  final Map<String, DateTime> _detailWrittenAt = <String, DateTime>{};
  int _requestEpoch = 0;
  int get requestEpoch => _requestEpoch;
  bool Function(ContentPostDetailPayload payload)? detailReplayPolicy;

  bool canReplayDetail(ContentPostDetailPayload payload) =>
      _namespace.isNotEmpty && (detailReplayPolicy?.call(payload) ?? false);

  void requireCurrentRequest(int epoch) {
    if (epoch != _requestEpoch) throw const CloudOperationCancelledException();
  }

  void adoptNamespace(ContentCacheIsolationIdentity identity) {
    if (_namespace != identity.cacheKeyPrefix) {
      _requestEpoch++;
      detailReplayPolicy = null;
    }
    _namespace = identity.cacheKeyPrefix;
  }

  void clearNamespace() {
    detailReplayPolicy = null;
    clearAllRebuildable();
    _namespace = '';
  }

  CacheReadResult<ContentPostDetailPayload>? getDetail(String postId) {
    if (_namespace.isEmpty) return null;
    final key = _objectKey(postId);
    final writtenAt = _detailWrittenAt[key];
    if (writtenAt == null ||
        _now().isBefore(writtenAt) ||
        _now().difference(writtenAt) >= detailsMaxAge) {
      _detailStore.remove(key);
      _detailWrittenAt.remove(key);
      return null;
    }
    return _detailStore.get(key);
  }

  CacheReadResult<ContentPostViewData>? getProjection(String postId) {
    return _projectionStore.get(_objectKey(postId));
  }

  void putDetail(ContentPostDetailPayload payload) {
    if (_namespace.isEmpty) return;
    final post = payload.post;
    _detailWrittenAt.removeWhere((key, _) => _detailStore.get(key) == null);
    _detailWrittenAt[_objectKey(post.id)] = _now();
    final version = _resolvePostVersion(post);
    _detailStore.put(
      _objectKey(post.id),
      payload,
      objectVersion: version,
      cacheClass: CacheClass.recent,
    );
    _detailWrittenAt.removeWhere((key, _) => _detailStore.get(key) == null);
    putProjection(post);
  }

  void putProjection(ContentPostViewData post) {
    if (post.id.trim().isEmpty) {
      return;
    }
    _projectionStore.put(
      _objectKey(post.id),
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
    _requestEpoch++;
    _detailWrittenAt.remove(_objectKey(normalized));
    _detailStore.remove(_objectKey(normalized));
    _projectionStore.remove(_objectKey(normalized));
  }

  int clearRecentDetails() {
    _requestEpoch++;
    _detailWrittenAt.clear();
    return _detailStore.clearAllRebuildable();
  }

  int clearAllRebuildable() {
    _requestEpoch++;
    _detailWrittenAt.clear();
    return _detailStore.clearAllRebuildable() +
        _projectionStore.clearAllRebuildable();
  }

  int get detailCount => _detailStore.count;

  int get projectionCount => _projectionStore.count;

  String _objectKey(String postId) {
    final normalized = postId.trim();
    return _namespace.isEmpty ? normalized : '$_namespace&postId=$normalized';
  }
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
    this.activationIdentity,
    this.objectCards = const <FeedObjectCard>[],
  }) {
    for (final card in objectCards) {
      if (card.anchorIndex < 0 || card.anchorIndex >= items.length) {
        throw const FormatException(
          'objectCard anchorIndex must identify an item',
        );
      }
    }
    final digest = policyDigest;
    if (digest != null && !isCanonicalSha256Digest(digest)) {
      throw const FormatException(
        'policyDigest must be a canonical SHA-256 digest',
      );
    }
    if (activationIdentity != null &&
        emptyReason == ContentFeedEmptyReason.noActiveRelease) {
      throw const FormatException(
        'no_active_release must not carry a content activation identity',
      );
    }
  }

  final String key;
  final List<ContentPostViewData> items;
  final List<FeedObjectCard> objectCards;
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

  /// 快照绑定的运行时内容激活身份；`null` 表示不绑定 release 的查询。
  final ContentActivationIdentity? activationIdentity;

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
      objectCards: objectCards,
      outcome: outcome,
      emptyReason: emptyReason,
      nextCursor: paginationIsUsable ? nextCursor : null,
      previousCursor: paginationIsUsable ? previousCursor : null,
      paginationExpiresAt: paginationIsUsable ? paginationExpiresAt : null,
      feedRequestId: feedRequestId,
      policyDigest: policyDigest,
      activationIdentity: activationIdentity,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'key': key,
      'items': items.map(_postSnapshotMap).toList(growable: false),
      'objectCards': objectCards
          .map((card) => card.toWire())
          .toList(growable: false),
      'nextCursor': nextCursor,
      'previousCursor': previousCursor,
      'paginationExpiresAt': paginationExpiresAt?.toUtc().toIso8601String(),
      'paginationSessionId': paginationSessionId,
      'fetchedAt': fetchedAt.toUtc().toIso8601String(),
      'feedRequestId': feedRequestId,
      'policyDigest': policyDigest,
      'outcome': outcome.name,
      'emptyReason': _feedEmptyReasonToWire(emptyReason),
      'activationReleaseId': activationIdentity?.releaseId,
      'activationManifestDigest': activationIdentity?.manifestDigest,
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
      if (rawItems.any((item) => item is! Map)) return null;
      final rawCards = map['objectCards'];
      if (rawCards is! List || rawCards.any((card) => card is! Map)) {
        return null;
      }
      final cards = rawCards
          .map(
            (card) =>
                FeedObjectCard.fromWire(Map<String, Object?>.from(card as Map)),
          )
          .toList(growable: false);
      final items = rawItems
          .cast<Map>()
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
        objectCards: List<FeedObjectCard>.unmodifiable(cards),
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
        activationIdentity: resolveContentActivationIdentity(
          releaseId: map['activationReleaseId']?.toString(),
          manifestDigest: map['activationManifestDigest']?.toString(),
          emptyReason: emptyReason,
        ),
      );
    } catch (error, stackTrace) {
      // 快照损坏时按「无缓存」继续，但损坏本身是真实故障，必须留证据。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.query_snapshot.decode',
          error: error,
          stackTrace: stackTrace,
        ),
      );
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
    return selectPersistableSnapshotChains(snapshots)
        .expand((chain) => chain)
        .toList(growable: false);
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
    this.hydrationDeadline = const Duration(milliseconds: 1500),
    bool persistToPreferences = false,
    String? storageKey,
    ContentQuerySnapshotPersistencePolicy persistencePolicy =
        const ContentQuerySnapshotPersistencePolicy(),
    ContentQuerySnapshotPersistenceBackend persistenceBackend =
        const SharedPreferencesContentQuerySnapshotPersistenceBackend(),
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
    DateTime Function()? now,
  }) : _persistToPreferences = persistToPreferences,
       // 显式 key 是调用方注入的完整存储身份；production 默认绑定已验证 target/env。
       _storageKey =
           storageKey ??
           (CloudRuntimeConfig.isHydrated
               ? '$defaultStorageKey.${Uri.encodeComponent('${CloudRuntimeConfig.launchTarget}|${CloudRuntimeConfig.appEnvironment}')}'
               : '$defaultStorageKey.unbound'),
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
    if (hydrationDeadline <= Duration.zero) {
      throw ArgumentError.value(
        hydrationDeadline,
        'hydrationDeadline',
        'must be positive',
      );
    }
  }

  static const String defaultStorageKey = 'qwq.content_query_snapshots';

  final int maxEntries;
  final Duration freshFor;
  final Duration maximumAge;
  final Duration hydrationDeadline;
  final bool _persistToPreferences;
  final String _storageKey;
  final ContentQuerySnapshotPersistencePolicy _persistencePolicy;
  final ContentQuerySnapshotPersistenceBackend _persistenceBackend;
  final CacheTelemetrySink _telemetrySink;
  final DateTime Function() _now;
  final LinkedHashMap<String, ContentQuerySnapshot> _snapshots =
      LinkedHashMap<String, ContentQuerySnapshot>();
  final Set<String> _diskBackedKeys = <String>{};
  Future<void>? _hydration;
  int _hydrationGeneration = 0;
  Future<void>? _persistenceDrain;
  bool _persistenceDirty = false;
  ContentCacheIsolationIdentity? _isolationIdentity;
  bool _principalIdentityAdopted = false;
  int _requestEpoch = 0;
  int get requestEpoch => _requestEpoch;

  /// composition 提供同步、本地的 public/visibility/permission 准入证明。
  /// 缺证明不回放；不得把远端 loader 或 last-confirmed 身份当授权。
  bool Function(ContentQuerySnapshot snapshot)? replayPolicy;

  bool canReplay(ContentQuerySnapshot snapshot) =>
      _isolationIdentity != null &&
      _isReplayable(snapshot) &&
      _snapshotAge(snapshot) < maximumAge &&
      (replayPolicy?.call(snapshot) ?? false);

  void requireCurrentRequest(int epoch) {
    if (epoch != _requestEpoch) throw const CloudOperationCancelledException();
  }

  void invalidateRequests() => _requestEpoch++;

  /// 采纳当前 production query/cache 的完整隔离身份。
  ///
  /// Research principal 在服务端确认 active release 前传 `null`，因此任何持久
  /// 快照都不可回放；权威首刷返回 tuple 后再传完整 identity。切换到不同的
  /// environment/audience/account/persona/sourceOwner/release tuple 时，由调用方
  /// 先清理可重建缓存，再采纳新身份。
  void adoptContentCacheIsolationIdentity(
    ContentCacheIsolationIdentity? identity,
  ) {
    if (_isolationIdentity != identity) {
      invalidateRequests();
      replayPolicy = null;
    }
    _isolationIdentity = identity;
    _principalIdentityAdopted = true;
  }

  bool _isReplayable(ContentQuerySnapshot snapshot) {
    if (!_principalIdentityAdopted) {
      return true;
    }
    final identity = _isolationIdentity;
    if (identity == null) {
      return false;
    }
    return snapshot.activationIdentity == identity.activationIdentity &&
        snapshot.key.startsWith('${identity.cacheKeyPrefix}&');
  }

  String? isolateQueryKey(
    String queryKey, {
    ContentCacheIsolationIdentity? identity,
  }) {
    final normalized = queryKey.trim();
    if (normalized.isEmpty) {
      throw const FormatException(
        'content cache query key must be a non-empty canonical value',
      );
    }
    final effectiveIdentity = identity ?? _isolationIdentity;
    if (effectiveIdentity == null) {
      return null;
    }
    return effectiveIdentity.isolateQueryKey(normalized);
  }

  Future<void> ensureHydrated() async {
    if (!_persistToPreferences) {
      return;
    }
    final existing = _hydration;
    final Future<void> hydration;
    if (existing != null) {
      hydration = existing;
    } else {
      final generation = ++_hydrationGeneration;
      hydration = _hydrateFromPreferences(generation);
      _hydration = hydration;
    }
    try {
      await hydration.timeout(hydrationDeadline);
    } catch (_) {
      if (identical(_hydration, hydration)) {
        _hydration = null;
        _hydrationGeneration += 1;
      }
    }
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
    if (age >= maximumAge) {
      _diskBackedKeys.remove(normalized);
      _schedulePersist();
      _telemetrySink.record('query_snapshot.expire', <String, Object?>{
        'count': 1,
        'source': 'read',
      });
      return null;
    }
    _snapshots[normalized] = snapshot;
    if (!_isReplayable(snapshot)) {
      return null;
    }
    final freshness = age < freshFor
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
    List<FeedObjectCard> objectCards = const <FeedObjectCard>[],
    String? nextCursor,
    String? previousCursor,
    DateTime? paginationExpiresAt,
    String? paginationSessionId,
    String? feedRequestId,
    String? policyDigest,
    ContentFeedOutcome outcome = ContentFeedOutcome.content,
    ContentFeedEmptyReason? emptyReason,
    ContentActivationIdentity? activationIdentity,
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
      objectCards: List<FeedObjectCard>.unmodifiable(objectCards),
      nextCursor: nextCursor,
      previousCursor: previousCursor,
      paginationExpiresAt: paginationExpiresAt,
      paginationSessionId: paginationSessionId,
      feedRequestId: feedRequestId,
      policyDigest: policyDigest,
      outcome: outcome,
      emptyReason: emptyReason,
      activationIdentity: activationIdentity,
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
    invalidateRequests();
    final count = _snapshots.length;
    _snapshots.clear();
    _diskBackedKeys.clear();
    _hydrationGeneration += 1;
    _hydration = null;
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

  Future<void> _hydrateFromPreferences(int generation) async {
    final raw = await _persistenceBackend.read(_storageKey);
    if (generation != _hydrationGeneration || raw == null || raw.isEmpty) {
      return;
    }
    if (_utf8WireLength(raw, stopAfter: _persistencePolicy.maxPersistedBytes) >
        _persistencePolicy.maxPersistedBytes) {
      // 通过既有单写 drain 清理，不能让旧 hydration 删除更新后的落盘值。
      _schedulePersist();
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
      if (_snapshotAge(snapshot) >= maximumAge) {
        expiredCount += 1;
        continue;
      }
      decodedSnapshots.add(snapshot);
    }
    if (generation != _hydrationGeneration) {
      return;
    }
    final persistableSnapshots = _persistencePolicy.selectPersistableSnapshots(
      decodedSnapshots,
    );
    var restoredCount = 0;
    for (final snapshot in persistableSnapshots) {
      final current = _snapshots[snapshot.key];
      if (current != null && !current.fetchedAt.isBefore(snapshot.fetchedAt)) {
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
    if (expiredCount > 0) {
      _telemetrySink.record('query_snapshot.expire', <String, Object?>{
        'count': expiredCount,
        'source': 'restore',
      });
      _schedulePersist();
    }
  }

  Duration _snapshotAge(ContentQuerySnapshot snapshot) {
    final age = _now().difference(snapshot.fetchedAt);
    // 时钟回退无法证明年龄，不把未来快照重新标为 fresh。
    return age.isNegative ? maximumAge : age;
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
