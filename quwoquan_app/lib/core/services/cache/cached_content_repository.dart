// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class CachedContentRepository
    implements ContentReadRepository, ContentWriteRepository {
  CachedContentRepository({
    required ContentReadRepository readDelegate,
    required ContentWriteRepository writeDelegate,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    UserProfileCacheService? userProfileCache,
    Future<List<String>> Function()? blockedKeywordsLoader,
    Future<void> Function(String avatarUrl)? avatarPreloader,
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
  }) : _readDelegate = readDelegate,
       _writeDelegate = writeDelegate,
       _postCache = postCache,
       _querySnapshotStore = querySnapshotStore,
       _userProfileCache = userProfileCache,
       _blockedKeywordsLoader = blockedKeywordsLoader ?? _emptyBlockedKeywords,
       _telemetrySink = telemetrySink,
       _avatarPreloader =
           avatarPreloader ?? AppImageCacheController.preloadAvatar;

  final ContentReadRepository _readDelegate;
  final ContentWriteRepository _writeDelegate;
  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final UserProfileCacheService? _userProfileCache;
  final Future<List<String>> Function() _blockedKeywordsLoader;
  final CacheTelemetrySink _telemetrySink;
  final Future<void> Function(String avatarUrl) _avatarPreloader;
  final Set<String> _inflightRefreshes = <String>{};

  static Future<List<String>> _emptyBlockedKeywords() async => const <String>[];

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
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
    await _querySnapshotStore.ensureHydrated();
    final cached = _querySnapshotStore.get(key);
    try {
      final page = await _readDelegate.listDiscoveryFeedPage(
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
      _storeFeedPage(key, page);
      return page;
    } catch (error) {
      if (cached != null) {
        final blockedKeywords = (await _blockedKeywordsLoader())
            .map((keyword) => keyword.trim().toLowerCase())
            .where((keyword) => keyword.isNotEmpty)
            .toSet();
        _recordCacheHit(key: key, result: cached);
        final cachedPage = cached.value.toDiscoveryFeedPage();
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
          nextCursor: cachedPage.nextCursor,
          feedRequestId: cachedPage.feedRequestId,
          rankingVersion: cachedPage.rankingVersion,
          reasonVersion: cachedPage.reasonVersion,
          cacheFallbackError: error,
          cacheAgeMs: _cacheAgeMs(cached.value.fetchedAt),
        );
      }
      rethrow;
    }
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    final cached = _postCache.getDetail(postId);
    if (cached != null) {
      _recordCacheHit(key: 'post:$postId', result: cached);
      if (cached.freshness != CacheFreshness.fresh) {
        unawaited(_refreshPost(postId));
      }
      return cached.value;
    }
    final payload = await _readDelegate.getPost(postId: postId);
    _storePostDetail(payload);
    return payload;
  }

  @override
  Future<void> deletePost({required String postId}) async {
    await _writeDelegate.deletePost(postId: postId);
    _postCache.removePost(postId);
    _querySnapshotStore.invalidatePost(postId);
    await _querySnapshotStore.flushPersistence();
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    final post = await _writeDelegate.updatePostSettings(
      postId: postId,
      body: body,
    );
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    final post = await _writeDelegate.promotePostToWork(
      postId: postId,
      body: body,
    );
    _storePostProjection(post);
    return post;
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final key = contentUserPostsQueryKey(
      userId: userId,
      identity: identity,
      type: type,
      cursor: cursor,
      limit: limit,
    );
    await _querySnapshotStore.ensureHydrated();
    final cached = _querySnapshotStore.get(key);
    try {
      final page = await _readDelegate.listUserPosts(
        userId: userId,
        identity: identity,
        type: type,
        cursor: cursor,
        limit: limit,
      );
      _storeCursorPage(key, page);
      return page;
    } catch (error) {
      if (cached != null) {
        _recordCacheHit(key: key, result: cached);
        final cachedPage = cached.value.toCursorPage();
        return CursorPage<PostBaseDto>(
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

  int _cacheAgeMs(DateTime fetchedAt) {
    return DateTime.now().difference(fetchedAt).inMilliseconds;
  }

  Future<void> _refreshPost(String postId) async {
    final key = 'post:$postId';
    if (!_inflightRefreshes.add(key)) {
      return;
    }
    try {
      final payload = await _readDelegate.getPost(postId: postId);
      _storePostDetail(payload);
    } finally {
      _inflightRefreshes.remove(key);
    }
  }

  void _storeFeedPage(String key, DiscoveryFeedPage page) {
    _storePostProjections(page.items);
    _querySnapshotStore.put(
      key: key,
      items: page.items,
      nextCursor: page.nextCursor,
      feedRequestId: page.feedRequestId,
      rankingVersion: page.rankingVersion,
      reasonVersion: page.reasonVersion,
    );
  }

  void _storeCursorPage(String key, CursorPage<PostBaseDto> page) {
    _storePostProjections(page.items);
    _querySnapshotStore.put(
      key: key,
      items: page.items,
      nextCursor: page.nextCursor,
    );
  }

  void _storePostDetail(ContentPostDetailPayload payload) {
    _postCache.putDetail(payload);
    _registerAuthorSnapshot(payload.post);
  }

  void _storePostProjection(PostBaseDto post) {
    _postCache.putProjection(post);
    _registerAuthorSnapshot(post);
  }

  void _storePostProjections(Iterable<PostBaseDto> posts) {
    final materialized = posts.toList(growable: false);
    _postCache.putProjections(materialized);
    for (final post in materialized) {
      _registerAuthorSnapshot(post);
    }
  }

  void _registerAuthorSnapshot(PostBaseDto post) {
    final avatarUrl = post.avatarUrl.trim();
    _userProfileCache?.putAuthorSnapshot(
      userId: post.subAccountId.trim().isNotEmpty
          ? post.subAccountId
          : post.authorId,
      displayName: post.displayName,
      avatarUrl: avatarUrl,
      backgroundUrl: post.authorBackgroundUrl,
      updatedAt: post.createdAt.toUtc().toIso8601String(),
    );
    if (avatarUrl.isNotEmpty) {
      unawaited(_avatarPreloader(avatarUrl).catchError((_) => null));
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
      'hitLayer': result.diagnostics.hitLayer,
    });
  }
}
