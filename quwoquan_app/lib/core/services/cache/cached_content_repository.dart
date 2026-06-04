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
  }) : _delegate = delegate,
       _postCache = postCache,
       _querySnapshotStore = querySnapshotStore,
       _userProfileCache = userProfileCache,
       _avatarPreloader =
           avatarPreloader ?? AppImageCacheController.preloadAvatar;

  final ContentRepository _delegate;
  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final UserProfileCacheService? _userProfileCache;
  final Future<void> Function(String avatarUrl) _avatarPreloader;
  final Set<String> _inflightRefreshes = <String>{};

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
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
    final cached = _querySnapshotStore.get(key);
    if (cached != null) {
      if (cached.freshness != CacheFreshness.fresh) {
        unawaited(
          _refreshFeedPage(
            key: key,
            category: category,
            identity: identity,
            type: type,
            subCategory: subCategory,
            limit: limit,
            cursor: cursor,
            sort: sort,
            sessionId: sessionId,
            feedRequestId: feedRequestId,
          ),
        );
      }
      return cached.value.toCursorPage();
    }
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
  Future<void> deletePost({required String postId}) {
    return _delegate.deletePost(postId: postId);
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
  Future<ContentRecommendationResponseDto> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return _delegate.getRecommendation(cursor: cursor, limit: limit);
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _delegate.listUserPosts(
      userId: userId,
      identity: identity,
      type: type,
      cursor: cursor,
      limit: limit,
    );
    _storePostProjections(page.items);
    return page;
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
  Future<void> favoritePost({required String postId}) {
    return _delegate.favoritePost(postId: postId);
  }

  @override
  Future<void> unfavoritePost({required String postId}) {
    return _delegate.unfavoritePost(postId: postId);
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
  }) {
    return _delegate.createComment(
      postId: postId,
      content: content,
      replyToCommentId: replyToCommentId,
      attachmentMediaIds: attachmentMediaIds,
      mentions: mentions,
      subAccountId: subAccountId,
      personaContextVersion: personaContextVersion,
    );
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) {
    return _delegate.deleteComment(postId: postId, commentId: commentId);
  }

  @override
  Future<void> likeComment({required String commentId}) {
    return _delegate.likeComment(commentId: commentId);
  }

  @override
  Future<void> unlikeComment({required String commentId}) {
    return _delegate.unlikeComment(commentId: commentId);
  }

  @override
  Future<CommentDto> reactToComment({
    required String commentId,
    required String reaction,
  }) {
    return _delegate.reactToComment(commentId: commentId, reaction: reaction);
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

  Future<void> _refreshFeedPage({
    required String key,
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    required int limit,
    String? cursor,
    required String sort,
    String? sessionId,
    String? feedRequestId,
  }) async {
    if (!_inflightRefreshes.add(key)) {
      return;
    }
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
    } finally {
      _inflightRefreshes.remove(key);
    }
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

  void _storeFeedPage(String key, CursorPage<PostBaseDto> page) {
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
}
