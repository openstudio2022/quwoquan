// ignore_for_file: prefer_initializing_formals

import 'dart:async';

import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

class CachedContentRepository implements ContentRepository {
  CachedContentRepository({
    required ContentRepository delegate,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    UserProfileCacheService? userProfileCache,
    Future<void> Function(String avatarUrl)? avatarPreloader,
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(),
  }) : _delegate = delegate,
       _postCache = postCache,
       _querySnapshotStore = querySnapshotStore,
       _userProfileCache = userProfileCache,
       _telemetrySink = telemetrySink,
       _avatarPreloader =
           avatarPreloader ?? AppImageCacheController.preloadAvatar;

  final ContentRepository _delegate;
  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final UserProfileCacheService? _userProfileCache;
  final CacheTelemetrySink _telemetrySink;
  final Future<void> Function(String avatarUrl) _avatarPreloader;
  final Set<String> _inflightRefreshes = <String>{};

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
  }) async {
    final key = contentFeedQueryKey(
      category: category,
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
      final page = await _delegate.listDiscoveryFeedPage(
        category: category,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
      );
      _storeFeedPage(key, page);
      return page;
    } catch (error) {
      if (cached != null) {
        _recordCacheHit(key: key, result: cached);
        final cachedPage = cached.value.toDiscoveryFeedPage();
        return DiscoveryFeedPage(
          items: cachedPage.items,
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
    final payload = await _delegate.getPost(postId: postId);
    _storePostDetail(payload);
    return payload;
  }

  @override
  Future<PostBaseDto> createPost({required CreatePostRequestWire body}) async {
    final post = await _delegate.createPost(body: body);
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> updatePost({
    required String postId,
    required UpdatePostRequestWire body,
  }) async {
    final post = await _delegate.updatePost(postId: postId, body: body);
    _storePostProjection(post);
    return post;
  }

  @override
  Future<void> deletePost({required String postId}) async {
    await _delegate.deletePost(postId: postId);
    _postCache.removePost(postId);
    _querySnapshotStore.invalidatePost(postId);
    await _querySnapshotStore.flushPersistence();
  }

  @override
  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  }) async {
    final post = await _delegate.publishPost(postId: postId, body: body);
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    final post = await _delegate.updatePostSettings(postId: postId, body: body);
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    final post = await _delegate.promotePostToWork(postId: postId, body: body);
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    final post = await _delegate.updatePostCircles(
      postId: postId,
      add: add,
      remove: remove,
    );
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    final post = await _delegate.repostToCircle(
      postId: postId,
      circleId: circleId,
    );
    _storePostProjection(post);
    return post;
  }

  @override
  Future<PostBaseDto> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    final post = await _delegate.quoteToCircle(
      postId: postId,
      circleId: circleId,
      quoteText: quoteText,
    );
    _storePostProjection(post);
    return post;
  }

  @override
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
  }) => _delegate.initMediaUpload(mediaType: mediaType);

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) => _delegate.completeMediaUpload(sessionId: sessionId);

  @override
  Future<void> abortMediaUpload({required String sessionId}) {
    return _delegate.abortMediaUpload(sessionId: sessionId);
  }

  @override
  Future<ContentMediaAssetWireDto> getMediaAsset({required String mediaId}) {
    return _delegate.getMediaAsset(mediaId: mediaId);
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectAutoVideoCover({
    required String mediaId,
  }) => _delegate.selectAutoVideoCover(mediaId: mediaId);

  @override
  Future<ContentVideoCoverSelectionWireDto> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) {
    return _delegate.selectManualVideoCover(
      mediaId: mediaId,
      coverAssetId: coverAssetId,
    );
  }

  @override
  Future<ContentArticleSummaryGenerateResponseDto> generateArticleSummary({
    required String title,
    required String body,
  }) {
    return _delegate.generateArticleSummary(title: title, body: body);
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
      final page = await _delegate.listUserPosts(
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

  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return _delegate.searchPosts(
      query: query,
      identity: identity,
      type: type,
      categoryId: categoryId,
      subCategory: subCategory,
      limit: limit,
    );
  }

  @override
  Future<void> likePost({required String postId}) {
    return _delegate.likePost(postId: postId);
  }

  @override
  Future<void> unlikePost({required String postId}) {
    return _delegate.unlikePost(postId: postId);
  }

  @override
  Future<bool> sharePost({required String postId}) {
    return _delegate.sharePost(postId: postId);
  }

  @override
  Future<bool> unsharePost({required String postId}) {
    return _delegate.unsharePost(postId: postId);
  }

  @override
  Future<ContentReactionState> getReactionState({required String postId}) {
    return _delegate.getReactionState(postId: postId);
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'recommended',
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return _delegate.listComments(
      postId: postId,
      cursor: cursor,
      sort: sort,
      limit: limit,
    );
  }

  @override
  Future<CommentCountsDelta> getCommentCountsDelta({
    required String postId,
    DateTime? since,
  }) {
    // 计数增量为实时小请求，直接透传 delegate（不进对象/快照缓存）。
    return _delegate.getCommentCountsDelta(postId: postId, since: since);
  }

  @override
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  }) {
    return _delegate.listCommentReplies(
      postId: postId,
      commentId: commentId,
      cursor: cursor,
      limit: limit,
    );
  }

  @override
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    List<String> attachmentMediaIds = const <String>[],
    List<Map<String, dynamic>> mentions = const <Map<String, dynamic>>[],
    String? subAccountId,
    String? personaContextVersion,
  }) async {
    final comment = await _delegate.createComment(
      postId: postId,
      content: content,
      replyToCommentId: replyToCommentId,
      attachmentMediaIds: attachmentMediaIds,
      mentions: mentions,
      subAccountId: subAccountId,
      personaContextVersion: personaContextVersion,
    );
    // 评论新增（一级评论与二级回复都计入 post 总数）后同步缓存的 post detail
    // commentCount，避免读详情缓存的消费者（详情页头部等）拿到陈旧计数，与
    // commentCount 单一真相源保持一致。
    _syncCachedDetailCommentCount(postId, 1);
    return comment;
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    await _delegate.deleteComment(postId: postId, commentId: commentId);
    _syncCachedDetailCommentCount(postId, -1);
  }

  @override
  Future<CommentDto> reactToComment({
    required String commentId,
    required String reaction,
  }) {
    return _delegate.reactToComment(commentId: commentId, reaction: reaction);
  }

  @override
  Future<CommentDto> setCommentPinned({
    required String postId,
    required String commentId,
    required bool pinned,
  }) {
    return _delegate.setCommentPinned(
      postId: postId,
      commentId: commentId,
      pinned: pinned,
    );
  }

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return _delegate.listCommentsByAuthor(cursor: cursor, limit: limit);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return _delegate.listCommentsForPostAuthor(cursor: cursor, limit: limit);
  }

  @override
  Future<ContentAppConfigWire> getAppConfig() {
    return _delegate.getAppConfig();
  }

  @override
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  }) {
    return _delegate.reportBehaviors(events: events);
  }

  @override
  Future<PostEngagementCounters> getCounters({required String postId}) {
    return _delegate.getCounters(postId: postId);
  }

  @override
  bool get requiresResolvedPersonaForMutations =>
      _delegate.requiresResolvedPersonaForMutations;

  @override
  bool get usesEmbeddedContentCatalog => _delegate.usesEmbeddedContentCatalog;

  @override
  bool get usesCloudAssistantEdgeSync => _delegate.usesCloudAssistantEdgeSync;

  @override
  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId) {
    return _delegate.discoveryPresentationWireForPost(postId);
  }

  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() {
    return _delegate.embeddedDiscoveryArticlePostsForFollowingMix();
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
      final payload = await _delegate.getPost(postId: postId);
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

  /// 评论增删后精确同步缓存的 post detail commentCount（命中缓存才生效）。
  /// 重建 detail payload 并 putDetail，连带刷新 projection，保证缓存层 getPost 的
  /// commentCount 与端侧单一真相源一致；下次远端 refresh 仍会以权威值覆盖。
  void _syncCachedDetailCommentCount(String postId, int delta) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return;
    }
    final cached = _postCache.getDetail(normalized);
    if (cached == null) {
      return;
    }
    final payload = cached.value;
    final current = payload.post.commentCount;
    final next = current + delta;
    final safeNext = next < 0 ? 0 : next;
    if (safeNext == current) {
      return;
    }
    final wire = Map<String, dynamic>.from(payload.mergedArticleWireMap);
    wire['commentCount'] = safeNext;
    _storePostDetail(ContentPostDetailPayload.fromWire(wire));
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
