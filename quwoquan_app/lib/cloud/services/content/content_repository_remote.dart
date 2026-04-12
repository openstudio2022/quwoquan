part of 'content_repository.dart';

PostBaseDto _postBaseDtoFromContentWire(Map<String, dynamic> obj) {
  final nested = obj['post'];
  if (nested is Map) {
    return postBaseDtoFromMap(Map<String, dynamic>.from(nested));
  }
  return postBaseDtoFromMap(obj);
}

CommentDto _commentDtoFromContentWire(Map<String, dynamic> obj) {
  final nested = obj['comment'];
  if (nested is Map) {
    return CommentDto.fromMap(Map<String, dynamic>.from(nested));
  }
  return CommentDto.fromMap(obj);
}
class RemoteContentRepository implements ContentRepository {
  RemoteContentRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final resolvedIdentity = identity ?? _mapCategoryToIdentity(category);
    final resolvedType = _normalizeFeedType(
      type ?? _mapCategoryToFeedType(category),
    );
    final query = <String, String>{};
    final keys = GeneratedPostRuntimeMetadata.feedQueryParams;
    if (keys.contains('identity') &&
        resolvedIdentity != null &&
        resolvedIdentity.isNotEmpty) {
      query['identity'] = resolvedIdentity;
    }
    if (keys.contains('type') &&
        resolvedType != null &&
        resolvedType.isNotEmpty &&
        !(resolvedIdentity == 'moment' && (type == null || type.isEmpty))) {
      query['type'] = resolvedType;
    }
    if (keys.contains('cursor') && cursor?.isNotEmpty == true) {
      query['cursor'] = cursor!;
    }
    if (keys.contains('sort') && sort.trim().isNotEmpty) {
      query['sort'] = sort.trim();
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && subCategory?.isNotEmpty == true) {
      query['subCategory'] = subCategory!;
    }
    final uri = _uri(ContentApiMetadata.getFeedPath, queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.getFeed,
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return CursorPage<PostBaseDto>(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
    );
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
    final uri = _uri(ContentApiMetadata.getPostPath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getPost),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getPost,
    );
    return ContentPostDetailPayload.fromWire(obj);
  }

  @override
  Future<PostBaseDto> createPost({
    required CreatePostRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.createPostPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.createPost),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.createPost,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<void> likePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.likePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.likePost),
      body: {},
    );
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.unlikePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.unlikePost),
    );
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.favoritePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.favoritePost),
      body: {},
    );
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.unfavoritePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.unfavoritePost,
      ),
    );
  }

  @override
  Future<ContentReactionState> getReactionState({
    required String postId,
  }) async {
    final uri = _uri(ContentApiMetadata.getReactionStatePath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getReactionState,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getReactionState,
    );
    return ContentReactionState.fromMap(obj);
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsPath(postId: postId),
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listComments),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listComments,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? personaId,
    String? profileSubjectId,
    String? personaContextVersion,
  }) async {
    final uri = _uri(ContentApiMetadata.createCommentPath(postId: postId));
    final body = <String, dynamic>{'content': content};
    if (replyToCommentId != null) body['replyToCommentId'] = replyToCommentId;
    if (personaId != null) body['personaId'] = personaId;
    if (profileSubjectId != null) body['profileSubjectId'] = profileSubjectId;
    if (personaContextVersion != null) {
      body['personaContextVersion'] = personaContextVersion;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.createComment),
      body: body,
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.createComment,
    );
    return _commentDtoFromContentWire(obj);
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.deleteCommentPath(
        postId: postId,
        commentId: commentId,
      ),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.deleteComment),
    );
  }

  @override
  Future<void> likeComment({required String commentId}) async {
    final uri = _uri(ContentApiMetadata.likeCommentPath(commentId: commentId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.likeComment),
      body: {},
    );
  }

  @override
  Future<void> unlikeComment({required String commentId}) async {
    final uri = _uri(
      ContentApiMetadata.unlikeCommentPath(commentId: commentId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.unlikeComment),
    );
  }

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsByAuthorPath,
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listCommentsByAuthor,
      ),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listCommentsByAuthor,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsForPostAuthorPath,
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listCommentsForPostAuthor,
      ),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listCommentsForPostAuthor,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    final uri = _uri(ContentApiMetadata.getAppConfigPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getAppConfig),
    );
    return ContentAppConfigWire.fromResponseObject(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.getAppConfig,
      ),
    );
  }

  @override
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  }) async {
    final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.reportBehaviors,
      ),
      body: <String, dynamic>{
        'events': events.map((e) => e.toRequestMap()).toList(growable: false),
      },
    );
  }

  @override
  Future<PostEngagementCounters> getCounters({required String postId}) async {
    final uri = _uri(ContentApiMetadata.getCountersPath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getCounters),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getCounters,
    );
    return PostEngagementCounters.fromMap(obj);
  }

  @override
  Future<PostBaseDto> updatePost({
    required String postId,
    required UpdatePostRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.updatePost),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePost,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<void> deletePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.deletePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.deletePost),
    );
  }

  @override
  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  }) async {
    final uri = _uri(ContentApiMetadata.publishPostPath(postId: postId));
    final wire = body ?? PublishPostRequestWire();
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.publishPost),
      body: wire.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.publishPost,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostSettingsPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updatePostSettings,
      ),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePostSettings,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    final uri = _uri(ContentApiMetadata.promotePostToWorkPath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.promotePostToWork,
      ),
      body: body.toWire(),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.promotePostToWork,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostCirclesPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updatePostCircles,
      ),
      body: {'add': add, 'remove': remove},
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePostCircles,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    final uri = _uri(ContentApiMetadata.repostToCirclePath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.repostToCircle,
      ),
      body: {'circleId': circleId},
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.repostToCircle,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<PostBaseDto> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    final uri = _uri(ContentApiMetadata.quoteToCirclePath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.quoteToCircle),
      body: {'circleId': circleId, 'quoteText': quoteText},
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.quoteToCircle,
    );
    return _postBaseDtoFromContentWire(obj);
  }

  @override
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
  }) async {
    final uri = _uri(ContentApiMetadata.initMediaUploadPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.initMediaUpload,
      ),
      body: {'mediaType': mediaType},
    );
    return ContentMediaInitUploadResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.initMediaUpload,
      ),
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.completeMediaUploadPath(sessionId: sessionId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.completeMediaUpload,
      ),
      body: {},
    );
    return ContentMediaCompleteUploadResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.completeMediaUpload,
      ),
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {
    final uri = _uri(
      ContentApiMetadata.abortMediaUploadPath(sessionId: sessionId),
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.abortMediaUpload,
      ),
      body: {},
    );
  }

  @override
  Future<ContentMediaAssetWireDto> getMediaAsset({required String mediaId}) async {
    final uri = _uri(ContentApiMetadata.getMediaAssetPath(mediaId: mediaId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getMediaAsset),
    );
    return ContentMediaAssetWireDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.getMediaAsset,
      ),
    );
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectAutoVideoCover({
    required String mediaId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.selectAutoVideoCoverPath(mediaId: mediaId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.selectAutoVideoCover,
      ),
      body: {},
    );
    return ContentVideoCoverSelectionWireDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.selectAutoVideoCover,
      ),
    );
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.selectManualVideoCoverPath(mediaId: mediaId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.selectManualVideoCover,
      ),
      body: {'coverAssetId': coverAssetId},
    );
    return ContentVideoCoverSelectionWireDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.selectManualVideoCover,
      ),
    );
  }

  @override
  Future<ContentArticleSummaryGenerateResponseDto> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    final uri = _uri(ContentApiMetadata.generateArticleSummaryPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.generateArticleSummary,
      ),
      body: {'title': title, 'body': body},
    );
    return ContentArticleSummaryGenerateResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.generateArticleSummary,
      ),
    );
  }

  @override
  Future<ContentRecommendationResponseDto> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(ContentApiMetadata.getRecommendationPath);
    final body = <String, dynamic>{'limit': limit};
    if (cursor != null && cursor.isNotEmpty) {
      body['cursor'] = cursor;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getRecommendation,
      ),
      body: body,
    );
    return ContentRecommendationResponseDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.getRecommendation,
      ),
    );
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    if (identity != null && identity.isNotEmpty) query['identity'] = identity;
    final resolvedType = _normalizeFeedType(type);
    if (resolvedType != null && resolvedType.isNotEmpty) {
      query['type'] = resolvedType;
    }
    final uri = _uri(
      ContentApiMetadata.listUserPostsPath(profileSubjectId: userId),
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listUserPosts),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listUserPosts,
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return CursorPage<PostBaseDto>(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
    );
  }

  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ContentApiMetadata.searchPostsPath,
      queryParameters: <String, String>{
        'query': query,
        if (identity != null && identity.isNotEmpty) 'identity': identity,
        if (type != null && type.isNotEmpty) 'type': type,
        if (categoryId != null && categoryId.isNotEmpty)
          'categoryId': categoryId,
        if (subCategory != null && subCategory.isNotEmpty)
          'subCategory': subCategory,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.searchPosts),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.searchPosts,
    );
    return rawPage.items
        .map(PostSearchItemView.fromMap)
        .toList(growable: false);
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }

  String? _mapCategoryToIdentity(String category) {
    switch (category.trim()) {
      case 'moment':
      case 'recommended':
      case 'following':
        return 'moment';
      case 'work':
      case 'works':
      case 'photo':
      case 'images':
      case 'video':
      case 'article':
        return 'work';
      default:
        return null;
    }
  }

  String? _normalizeFeedType(String? type) {
    final normalized = (type ?? '').trim().toLowerCase();
    switch (normalized) {
      case '':
        return null;
      case 'photo':
        return 'image';
      case 'note':
        return 'article';
      default:
        return normalized;
    }
  }

  @override
  bool get requiresResolvedPersonaForMutations => true;

  @override
  bool get usesEmbeddedContentCatalog => false;

  @override
  bool get usesCloudAssistantEdgeSync => true;

  @override
  Map<String, dynamic>? discoveryPresentationWireForPost(String postId) => null;

  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() =>
      const <PostBaseDto>[];
}
