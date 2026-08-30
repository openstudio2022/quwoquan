// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_author_snapshot_cache.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts
    show ContentDiscoveryFeedQuery;

class CachedContentRepository
    implements ContentDiscoveryFeedQuery, ContentPostDeleteCommandWriter {
  CachedContentRepository({
    required ContentDiscoveryFeedQuery feedDelegate,
    required ContentPostDeleteCommandWriter deleteDelegate,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    UserProfileAuthorSnapshotCache? userProfileCache,
    Future<List<String>> Function()? blockedKeywordsLoader,
    // 契约：best-effort 预热，失败自行留痕、不向上抛。
    Future<void> Function(String avatarUrl)? avatarPreloader,
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
  }) : _feedDelegate = feedDelegate,
       _deleteDelegate = deleteDelegate,
       _postCache = postCache,
       _querySnapshotStore = querySnapshotStore,
       _userProfileCache = userProfileCache,
       _blockedKeywordsLoader = blockedKeywordsLoader ?? _emptyBlockedKeywords,
       _telemetrySink = telemetrySink,
       _avatarPreloader =
           avatarPreloader ?? AppImageCacheController.warmAvatarCache;

  final ContentDiscoveryFeedQuery _feedDelegate;
  final ContentPostDeleteCommandWriter _deleteDelegate;
  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final UserProfileAuthorSnapshotCache? _userProfileCache;
  final Future<List<String>> Function() _blockedKeywordsLoader;
  final CacheTelemetrySink _telemetrySink;
  final Future<void> Function(String avatarUrl) _avatarPreloader;
  static Future<List<String>> _emptyBlockedKeywords() async => const <String>[];

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = contracts.ContentDiscoveryFeedQuery.defaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final key = contentFeedQueryKey(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      cursor: cursor,
      sort: sort,
      limit: limit,
    );
    await runCloudOperationPrerequisite(
      _querySnapshotStore.ensureHydrated,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    final cached = _querySnapshotStore.get(key);
    final isInitialPage = cursor == null || cursor.trim().isEmpty;
    if (cached != null && isInitialPage) {
      final cachedPage = await _visibleCachedFeedPage(
        key: key,
        cached: cached,
        sessionId: sessionId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
      final revalidation = _revalidateFeedPage(
        cachedPage: cachedPage,
        key: key,
        category: category,
        channelId: channelId,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
      return _copyFeedPage(cachedPage, revalidation: revalidation);
    }
    try {
      return await _fetchAndStoreFeedPage(
        key: key,
        category: category,
        channelId: channelId,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
    } catch (error) {
      if (cached != null) {
        final cachedPage = await _visibleCachedFeedPage(
          key: key,
          cached: cached,
          sessionId: sessionId,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        );
        return _copyFeedPage(cachedPage, cacheFallbackError: error);
      }
      rethrow;
    }
  }

  Future<DiscoveryFeedPage> _fetchAndStoreFeedPage({
    required String key,
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    required int limit,
    String? cursor,
    required String sort,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final page = await _feedDelegate.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    _storeFeedPage(
      key,
      page,
      sessionId: sessionId,
      isInitialPage: cursor == null || cursor.trim().isEmpty,
    );
    return page;
  }

  Future<DiscoveryFeedPage> _visibleCachedFeedPage({
    required String key,
    required CacheReadResult<ContentQuerySnapshot> cached,
    String? sessionId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final blockedKeywords =
        (await runCloudOperationPrerequisite(
              _blockedKeywordsLoader,
              cancellation: cancellation,
              deadlineAt: deadlineAt,
            ))
            .map((keyword) => keyword.trim().toLowerCase())
            .where((keyword) => keyword.isNotEmpty)
            .toSet();
    _recordCacheHit(key: key, result: cached);
    final cachedPage = cached.value.toDiscoveryFeedPage(
      currentSessionId: sessionId,
    );
    final visibleItems = blockedKeywords.isEmpty
        ? cachedPage.items
        : cachedPage.items
              .where((item) {
                final searchable = '${item.title} ${item.normalizedBody}'
                    .toLowerCase();
                return !blockedKeywords.any(searchable.contains);
              })
              .toList(growable: false);
    return DiscoveryFeedPage(
      items: visibleItems,
      outcome: cachedPage.outcome,
      emptyReason: cachedPage.emptyReason,
      objectCards: cachedPage.objectCards,
      nextCursor: cachedPage.nextCursor,
      previousCursor: cachedPage.previousCursor,
      paginationExpiresAt: cachedPage.paginationExpiresAt,
      feedRequestId: cachedPage.feedRequestId,
      policyDigest: cachedPage.policyDigest,
      activationIdentity: cachedPage.activationIdentity,
      cacheAgeMs: _cacheAgeMs(cached.value.fetchedAt),
    );
  }

  Future<DiscoveryFeedPage> _revalidateFeedPage({
    required DiscoveryFeedPage cachedPage,
    required String key,
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    required int limit,
    String? cursor,
    required String sort,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    try {
      return await _fetchAndStoreFeedPage(
        key: key,
        category: category,
        channelId: channelId,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
    } catch (error) {
      return _copyFeedPage(cachedPage, cacheFallbackError: error);
    }
  }

  DiscoveryFeedPage _copyFeedPage(
    DiscoveryFeedPage page, {
    Object? cacheFallbackError,
    Future<DiscoveryFeedPage>? revalidation,
  }) {
    return DiscoveryFeedPage(
      items: page.items,
      outcome: page.outcome,
      emptyReason: page.emptyReason,
      objectCards: page.objectCards,
      nextCursor: page.nextCursor,
      previousCursor: page.previousCursor,
      paginationExpiresAt: page.paginationExpiresAt,
      feedRequestId: page.feedRequestId,
      policyDigest: page.policyDigest,
      activationIdentity: page.activationIdentity,
      cacheFallbackError: cacheFallbackError,
      cacheAgeMs: page.cacheAgeMs,
      revalidation: revalidation,
    );
  }

  @override
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  }) async {
    final receipt = await _deleteDelegate.deletePost(
      postId: postId,
      idempotencyKey: idempotencyKey,
    );
    _postCache.removePost(postId);
    _querySnapshotStore.invalidatePost(postId);
    await _querySnapshotStore.flushPersistence();
    return receipt;
  }

  int _cacheAgeMs(DateTime fetchedAt) {
    return DateTime.now().difference(fetchedAt).inMilliseconds;
  }

  void _storeFeedPage(
    String key,
    DiscoveryFeedPage page, {
    String? sessionId,
    required bool isInitialPage,
  }) {
    _storePostProjections(page.items);
    // 远端权威响应驱动运行时内容身份：新 digest 原子切 namespace，
    // no_active_release 停止回放 release-bound 快照。continuation 页冻结
    // 首刷身份，不参与采纳（避免回放旧 release 时倒灌身份）。
    if (isInitialPage) {
      _querySnapshotStore.adoptContentActivationIdentity(
        page.activationIdentity,
      );
    }
    _querySnapshotStore.put(
      key: key,
      items: page.items,
      nextCursor: page.nextCursor,
      previousCursor: page.previousCursor,
      paginationExpiresAt: page.paginationExpiresAt,
      paginationSessionId: sessionId,
      feedRequestId: page.feedRequestId,
      policyDigest: page.policyDigest,
      outcome: page.outcome,
      emptyReason: page.emptyReason,
      activationIdentity: page.activationIdentity,
    );
  }

  void _storePostProjections(Iterable<ContentPostViewData> posts) {
    final materialized = posts.toList(growable: false);
    _postCache.putProjections(materialized);
    for (final post in materialized) {
      _registerAuthorSnapshot(post);
    }
  }

  void _registerAuthorSnapshot(ContentPostViewData post) {
    final avatarUrl = post.avatarUrl.trim();
    _userProfileCache?.putAuthorSnapshot(
      userId: post.personaId.trim().isNotEmpty ? post.personaId : post.authorId,
      displayName: post.displayName,
      avatarUrl: avatarUrl,
      backgroundUrl: post.authorBackgroundUrl,
      updatedAt: post.createdAt.toUtc().toIso8601String(),
    );
    if (avatarUrl.isNotEmpty) {
      unawaited(_avatarPreloader(avatarUrl));
    }
  }

  void _recordCacheHit<T>({
    required String key,
    required CacheReadResult<T> result,
  }) {
    _telemetrySink.record('cache.hit.source', <String, Object?>{
      'key': key,
      'source': result.source.name,
      'freshness': result.freshness.name,
      'cacheClass': result.cacheClass.name,
      'hitLayer': result.diagnostics.hitLayer,
    });
  }
}
