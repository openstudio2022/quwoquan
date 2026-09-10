import 'dart:async';

import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_author_snapshot_cache.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

/// 详情与作者作品列表的缓存 Reader。
///
/// transport Reader 仅承载生成 operation；缓存、作者快照和图片预热仍在此 App
/// 层完成，避免把详情的页面性能策略带回 Remote adapter。
final class CachedContentPostReader
    implements ContentPostDetailReader, ContentAuthorPostsReader {
  CachedContentPostReader({
    required this.detailDelegate,
    required this.authorPostsDelegate,
    required this.postCache,
    required this.querySnapshotStore,
    required this.currentCacheIdentity,
    this.userProfileCache,
    // 契约：best-effort 预热，失败自行留痕、不向上抛。
    Future<void> Function(String avatarUrl)? avatarPreloader,
    this.telemetrySink = const DeveloperLogCacheTelemetrySink(),
  }) : _avatarPreloader =
           avatarPreloader ?? AppImageCacheController.warmAvatarCache;

  final ContentPostDetailReader detailDelegate;
  final ContentAuthorPostsReader authorPostsDelegate;
  final PostObjectCacheService postCache;
  final ContentQuerySnapshotStore querySnapshotStore;
  final ContentCacheIsolationIdentity? Function() currentCacheIdentity;
  final UserProfileAuthorSnapshotCache? userProfileCache;
  final Future<void> Function(String avatarUrl) _avatarPreloader;
  final CacheTelemetrySink telemetrySink;
  final Set<String> _inflightRefreshes = <String>{};

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    final requestEpoch = postCache.requestEpoch;
    final cached = postCache.getDetail(postId);
    if (cached != null && postCache.canReplayDetail(cached.value)) {
      _recordCacheHit(key: 'post:$postId', result: cached);
      if (cached.freshness != CacheFreshness.fresh) {
        unawaited(_refreshPost(postId));
      }
      return cached.value;
    }
    try {
      final payload = await detailDelegate.getPost(
        postId: postId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
      throwIfCloudOperationInterrupted(
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
      postCache.requireCurrentRequest(requestEpoch);
      _storePostDetail(payload);
      return payload;
    } catch (error) {
      postCache.requireCurrentRequest(requestEpoch);
      if (!isContentCacheTransportFallback(error, deadlineAt: deadlineAt)) {
        postCache.removePost(postId);
      }
      rethrow;
    }
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) async {
    final baseKey = contentUserPostsQueryKey(
      userId: userId,
      identity: identity,
      type: type,
      visibility: visibility,
      cursor: cursor,
      limit: limit,
    );
    final requestEpoch = querySnapshotStore.requestEpoch;
    final requestCacheIdentity = currentCacheIdentity();
    final key = querySnapshotStore.isolateQueryKey(
      baseKey,
      identity: requestCacheIdentity,
    );
    await querySnapshotStore.ensureHydrated();
    querySnapshotStore.requireCurrentRequest(requestEpoch);
    final candidate = key == null ? null : querySnapshotStore.get(key);
    final cached =
        candidate != null && querySnapshotStore.canReplay(candidate.value)
        ? candidate
        : null;
    if (cached != null && cached.freshness == CacheFreshness.fresh) {
      return cached.value.toCursorPage();
    }
    try {
      final page = await authorPostsDelegate.listUserPosts(
        userId: userId,
        identity: identity,
        type: type,
        visibility: visibility,
        cursor: cursor,
        limit: limit,
      );
      querySnapshotStore.requireCurrentRequest(requestEpoch);
      final responseCacheIdentity = currentCacheIdentity();
      if (requestCacheIdentity == responseCacheIdentity) {
        _storeCursorPage(key, page, cacheIdentity: responseCacheIdentity);
      }
      return page;
    } catch (error) {
      querySnapshotStore.requireCurrentRequest(requestEpoch);
      if (!isContentCacheTransportFallback(error)) {
        postCache.clearNamespace();
        querySnapshotStore.clearAll();
        rethrow;
      }
      if (isContentCacheTransportFallback(error) &&
          cached != null &&
          querySnapshotStore.canReplay(cached.value)) {
        _recordCacheHit(key: key!, result: cached);
        final cachedPage = cached.value.toCursorPage();
        return CursorPage<ContentPostViewData>(
          items: cachedPage.items,
          nextCursor: cachedPage.nextCursor,
          totalCount: cachedPage.totalCount,
          cacheFallbackError: error,
          cacheAgeMs: _cacheAgeMs(cached.value.fetchedAt),
        );
      }
      rethrow;
    }
  }

  Future<void> _refreshPost(String postId) async {
    final requestEpoch = postCache.requestEpoch;
    final key = '$requestEpoch:post:$postId';
    if (!_inflightRefreshes.add(key)) {
      return;
    }
    try {
      final payload = await detailDelegate.getPost(postId: postId);
      postCache.requireCurrentRequest(requestEpoch);
      _storePostDetail(payload);
    } catch (error) {
      if (postCache.requestEpoch == requestEpoch &&
          !isContentCacheTransportFallback(error)) {
        postCache.removePost(postId);
      }
      telemetrySink.record('cache.refresh_failed', <String, Object?>{
        'staleContext': postCache.requestEpoch != requestEpoch,
        'errorType': error.runtimeType.toString(),
      });
    } finally {
      _inflightRefreshes.remove(key);
    }
  }

  void _storeCursorPage(
    String? key,
    CursorPage<ContentPostViewData> page, {
    required ContentCacheIsolationIdentity? cacheIdentity,
  }) {
    if (key == null || cacheIdentity == null) {
      return;
    }
    postCache.putProjections(page.items);
    for (final post in page.items) {
      _registerAuthorSnapshot(post);
    }
    querySnapshotStore.put(
      key: key,
      items: page.items,
      nextCursor: page.nextCursor,
      activationIdentity: cacheIdentity.activationIdentity,
    );
  }

  void _storePostDetail(ContentPostDetailPayload payload) {
    postCache.putDetail(payload);
    _registerAuthorSnapshot(payload.post);
  }

  void _registerAuthorSnapshot(ContentPostViewData post) {
    final avatarUrl = post.avatarUrl.trim();
    userProfileCache?.putAuthorSnapshot(
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

  int _cacheAgeMs(DateTime fetchedAt) {
    return DateTime.now().difference(fetchedAt).inMilliseconds;
  }

  void _recordCacheHit<T>({
    required String key,
    required CacheReadResult<T> result,
  }) {
    telemetrySink.record('cache.hit.source', <String, Object?>{
      'key': key,
      'source': result.source.name,
      'freshness': result.freshness.name,
      'hitLayer': result.diagnostics.hitLayer,
    });
  }
}
