part of 'content_repository.dart';

class MockContentRepository implements ContentRepository {
  MockContentRepository({List<PostBaseDto>? seedPosts})
    : _seedPosts = seedPosts ?? _contractSeedPosts();

  final List<PostBaseDto>? _seedPosts;

  static List<PostBaseDto>? _contractSeedPosts() {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet();
    final posts = seed?['posts'];
    final contractPosts = <PostBaseDto>[];
    if (posts is! List) {
      return null;
    }
    contractPosts.addAll(
      posts
          .whereType<Map>()
          .map((item) => postBaseDtoFromMap(item.cast<String, dynamic>()))
          .toList(growable: false),
    );
    return _mergePostSeeds(_discoverySeedPosts(), contractPosts);
  }

  static List<PostBaseDto> _discoverySeedPosts() {
    return aggregateDiscoveryWireSlices(
      photo: ContentMockData.discoveryPhotoData,
      video: ContentMockData.discoveryVideoData,
      moment: ContentMockData.discoveryMomentData,
      article: ContentMockData.discoveryArticleData,
    ).map(postBaseDtoFromMap).toList(growable: false);
  }

  static List<PostBaseDto> _mergePostSeeds(
    List<PostBaseDto> primary,
    List<PostBaseDto> fallback,
  ) {
    final byId = <String, PostBaseDto>{};
    for (final post in primary) {
      byId[post.id] = post;
    }
    for (final post in fallback) {
      byId.putIfAbsent(post.id, () => post);
    }
    return byId.values.toList(growable: false);
  }

  Exception? throwOnLike;
  Exception? throwOnCreateComment;
  Exception? throwOnFavorite;
  Exception? throwOnShare;

  int likePostCallCount = 0;
  int createCommentCallCount = 0;
  int sharePostCallCount = 0;
  String? lastCommentText;
  String? lastCommentPostId;

  Map<String, dynamic> reactionStateStub = {
    'liked': false,
    'favorited': false,
    'shared': false,
  };
  List<CommentDto> commentsStub = [];
  int countersStubLikeCount = 0;
  int countersStubCommentCount = 0;
  int countersStubShareCount = 0;

  PostBaseDto _mockPostDto(
    String postId, {
    required Map<String, dynamic> payloadMerge,
  }) {
    return postBaseDtoFromMap(
      _mockPostWire(postId, payloadMerge: payloadMerge),
    );
  }

  Map<String, dynamic> _mockPostWire(
    String postId, {
    required Map<String, dynamic> payloadMerge,
  }) {
    final merged = <String, dynamic>{
      'postId': postId,
      '_id': postId,
      'id': postId,
      'authorId': 'mock_user',
      'displayName': 'Mock User',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'body': '',
      'mediaUrls': <String>[],
      'likeCount': 0,
      'commentCount': 0,
      'favoriteCount': 0,
      'shareCount': 0,
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
      'createdAt': DateTime.now().toUtc().toIso8601String(),
      'assistantUsePolicy': 'inherit',
      ...payloadMerge,
    };
    final rawType = (merged['contentType'] ?? merged['type'] ?? 'micro')
        .toString();
    final normalizedType = rawType == 'moment' ? 'micro' : rawType;
    merged['contentType'] = normalizedType;
    if (normalizedType == 'micro') {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'moment';
      merged['identity'] = merged['identity'] ?? 'moment';
    } else {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'work';
      merged['identity'] = merged['identity'] ?? 'work';
    }
    return merged;
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
    String? sessionId,
    String? feedRequestId,
  }) async {
    final items = _resolveDiscoveryPosts(
      category: category,
      identity: identity,
      type: type,
    );
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
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
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <PostSearchItemView>[];
    }
    final expectedIdentity = (identity ?? '').trim().toLowerCase();
    final expectedType = (type ?? '').trim().toLowerCase();
    final expectedCategoryId = (categoryId ?? '').trim().toLowerCase();
    final expectedSubCategory = (subCategory ?? '').trim().toLowerCase();
    final allRaw = _allDiscoveryPosts().map((e) => e.toMap()).toList();
    final results = <PostSearchItemView>[];
    for (final item in allRaw) {
      final circleIds = <String>{
        if ((item['circleId'] ?? '').toString().trim().isNotEmpty)
          (item['circleId'] ?? '').toString().trim(),
        ...((item['circleIds'] as List?)
                ?.map((value) => value.toString().trim())
                .where((value) => value.isNotEmpty) ??
            const <String>[]),
      };
      final associatedCircles = circleIds
          .map(CircleMockData.tryResolveCircleDto)
          .whereType<CircleDto>()
          .toList(growable: false);
      final matchedCategory = associatedCircles
          .where(
            (circle) =>
                (expectedCategoryId.isEmpty ||
                    (circle.category ?? '').toLowerCase() ==
                        expectedCategoryId) &&
                (expectedSubCategory.isEmpty ||
                    (circle.subCategory ?? '').toLowerCase() ==
                        expectedSubCategory),
          )
          .toList(growable: false);
      final matchedCircle = matchedCategory.isNotEmpty
          ? matchedCategory.first
          : (associatedCircles.isEmpty ? null : associatedCircles.first);
      final fallbackCategoryId = _mockCategoryForCircleIds(circleIds);
      final itemIdentity =
          (item['contentIdentity'] ??
                  (item['contentType'] == 'micro' ? 'moment' : 'work'))
              .toString()
              .toLowerCase();
      final itemType = (item['contentType'] ?? item['type'] ?? '')
          .toString()
          .toLowerCase();
      final itemCategoryId =
          (item['categoryId'] ?? matchedCircle?.category ?? fallbackCategoryId)
              .toString()
              .toLowerCase();
      final itemSubCategory =
          (item['subCategory'] ?? matchedCircle?.subCategory ?? '')
              .toString()
              .toLowerCase();
      if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
        continue;
      }
      if (expectedType.isNotEmpty && itemType != expectedType) {
        continue;
      }
      if (expectedCategoryId.isNotEmpty &&
          itemCategoryId != expectedCategoryId) {
        continue;
      }
      if (expectedSubCategory.isNotEmpty &&
          itemSubCategory != expectedSubCategory) {
        continue;
      }
      final searchable = <String>[
        item['title']?.toString() ?? '',
        item['displayName']?.toString() ?? '',
        item['body']?.toString() ?? '',
        item['summary']?.toString() ?? '',
        item['locationName']?.toString() ?? '',
      ];
      final matched = searchable.firstWhere(
        (value) => value.toLowerCase().contains(normalizedQuery),
        orElse: () => '',
      );
      if (matched.isEmpty) {
        continue;
      }
      results.add(
        PostSearchItemView.fromMap(<String, dynamic>{
          ...item,
          'categoryId': item['categoryId'] ?? matchedCircle?.category,
          'subCategory': item['subCategory'] ?? matchedCircle?.subCategory,
          'highlightText': matched,
          'matchedField': matched == (item['title']?.toString() ?? '')
              ? 'title'
              : matched == (item['displayName']?.toString() ?? '')
              ? 'author'
              : 'body',
          'authorId': item['authorId'] ?? item['subAccountId'] ?? '',
          'authorDisplayName':
              item['displayName'] ?? item['authorDisplayNameSnapshot'] ?? '',
          'authorAvatarUrl':
              item['authorAvatarUrl'] ?? item['authorAvatarUrlSnapshot'] ?? '',
        }),
      );
    }
    results.sort((a, b) {
      final aAuthorMatch = a.matchedField == 'author' ? 0 : 1;
      final bAuthorMatch = b.matchedField == 'author' ? 0 : 1;
      final byAuthor = aAuthorMatch.compareTo(bAuthorMatch);
      if (byAuthor != 0) {
        return byAuthor;
      }
      return a.postId.compareTo(b.postId);
    });
    return results.take(limit).toList(growable: false);
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    final raw = lookupCanonicalDiscoveryWireRowByPostId(postId);
    if (raw == null) {
      return Future.error(Exception('Post $postId not found'));
    }
    return ContentPostDetailPayload.fromWire(raw);
  }

  @override
  Future<PostBaseDto> createPost({required CreatePostRequestWire body}) async {
    final postId = 'local_${DateTime.now().millisecondsSinceEpoch}';
    return _mockPostDto(postId, payloadMerge: body.toWire());
  }

  @override
  Future<void> likePost({required String postId}) async {
    likePostCallCount++;
    if (throwOnLike != null) throw throwOnLike!;
    countersStubLikeCount++;
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    likePostCallCount++;
    if (throwOnLike != null) throw throwOnLike!;
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    if (throwOnFavorite != null) throw throwOnFavorite!;
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {}

  @override
  Future<bool> sharePost({required String postId}) async {
    sharePostCallCount++;
    if (throwOnShare != null) {
      throw throwOnShare!;
    }
    final changed = reactionStateStub['shared'] != true;
    reactionStateStub = {...reactionStateStub, 'shared': true};
    if (changed) {
      countersStubShareCount++;
    }
    return changed;
  }

  @override
  Future<bool> unsharePost({required String postId}) async {
    final changed = reactionStateStub['shared'] == true;
    reactionStateStub = {...reactionStateStub, 'shared': false};
    if (changed && countersStubShareCount > 0) {
      countersStubShareCount--;
    }
    return changed;
  }

  @override
  Future<ContentReactionState> getReactionState({
    required String postId,
  }) async {
    return ContentReactionState.fromMap({
      ...reactionStateStub,
      'postId': postId,
    });
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return CommentPage(
      items: List<CommentDto>.from(commentsStub),
      nextCursor: null,
    );
  }

  @override
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? subAccountId,
    String? personaContextVersion,
  }) async {
    createCommentCallCount++;
    lastCommentPostId = postId;
    lastCommentText = content;
    if (throwOnCreateComment != null) throw throwOnCreateComment!;
    final comment = <String, dynamic>{
      '_id': 'mock_comment_${DateTime.now().millisecondsSinceEpoch}',
      'postId': postId,
      'content': content,
      'authorId': 'mock_user',
      'subAccountId': subAccountId ?? 'mock_user',
      'personaContextVersion': personaContextVersion,
      'replyCount': 0,
      'likeCount': 0,
      'status': 'visible',
      'isAuthor': false,
      'createdAt': DateTime.now().toIso8601String(),
    };
    if (replyToCommentId != null) {
      comment['replyToCommentId'] = replyToCommentId;
    }
    final dto = CommentDto.fromMap(comment);
    commentsStub = [...commentsStub, dto];
    countersStubCommentCount++;
    return dto;
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    commentsStub = commentsStub.where((c) => c.id != commentId).toList();
  }

  @override
  Future<void> likeComment({required String commentId}) async {}

  @override
  Future<void> unlikeComment({required String commentId}) async {}

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null);
  }

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    return ContentAppConfigWire.fromResponseObject({
      'content': {
        'comment': {
          'max_length': 500,
          'reply_preview_count': 3,
          'fold_line_count': 3,
        },
        'feature_flags': {
          'enable_create_action_entry': true,
          'enable_unified_create_editor': true,
          'simple_create_action_sheet': true,
          'progressive_title_prompt': true,
          'enable_identity_based_surfaces': true,
          'enable_identity_share_template': true,
          'enable_article_distribution_profiles': true,
          'enable_article_book_reader': true,
          'enable_article_page_curl': true,
          'enable_assistant_content_identity_index': true,
        },
        'gray_release': {
          'experiment_bucket': 'local_story_enabled',
          'current_stage': '100%',
          'canary_matrix': [
            {'stage': '5%', 'rolloutPercent': 5},
            {'stage': '20%', 'rolloutPercent': 20},
            {'stage': '50%', 'rolloutPercent': 50},
            {'stage': '100%', 'rolloutPercent': 100},
          ],
        },
      },
    });
  }

  @override
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  }) async {}

  @override
  Future<PostEngagementCounters> getCounters({required String postId}) async {
    return PostEngagementCounters(
      likeCount: countersStubLikeCount,
      commentCount: countersStubCommentCount,
      shareCount: countersStubShareCount,
    );
  }

  @override
  Future<PostBaseDto> updatePost({
    required String postId,
    required UpdatePostRequestWire body,
  }) async {
    return _mockPostDto(
      postId,
      payloadMerge: {...body.toWire(), 'postId': postId},
    );
  }

  @override
  Future<void> deletePost({required String postId}) async {}

  @override
  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  }) async {
    final wire = body ?? PublishPostRequestWire();
    return _mockPostDto(
      postId,
      payloadMerge: {...wire.toWire(), 'postId': postId, 'status': 'published'},
    );
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    return _mockPostDto(
      postId,
      payloadMerge: {...body.toWire(), 'postId': postId},
    );
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    return _mockPostDto(
      postId,
      payloadMerge: {
        ...body.toWire(),
        'postId': postId,
        'contentIdentity': 'work',
        'identity': 'work',
        'status': 'published',
      },
    );
  }

  @override
  Future<PostBaseDto> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    return _mockPostDto(
      postId,
      payloadMerge: {'postId': postId, 'circleIds': add},
    );
  }

  @override
  Future<PostBaseDto> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    final newId = 'local_repost_${DateTime.now().millisecondsSinceEpoch}';
    return _mockPostDto(
      newId,
      payloadMerge: {'circleId': circleId, 'sourcePostId': postId},
    );
  }

  @override
  Future<PostBaseDto> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    final newId = 'local_quote_${DateTime.now().millisecondsSinceEpoch}';
    return _mockPostDto(
      newId,
      payloadMerge: {
        'body': quoteText,
        'circleId': circleId,
        'sourcePostId': postId,
      },
    );
  }

  @override
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
  }) async {
    final ts = DateTime.now().millisecondsSinceEpoch;
    return ContentMediaInitUploadResponseDto(
      sessionId: 'mock_upload_$ts',
      mediaId: 'mock_media_$ts',
      uploadUrl: 'https://origin.example/upload/mock_media_$ts',
      presignUrl: 'https://origin.example/upload/mock_media_$ts',
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    return ContentMediaCompleteUploadResponseDto(
      sessionId: sessionId,
      status: 'ready',
      cdnUrl: 'https://cdn.example/media/mock',
      assetId: 'mock_media_$sessionId',
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {}

  @override
  Future<ContentMediaAssetWireDto> getMediaAsset({
    required String mediaId,
  }) async {
    return ContentMediaAssetWireDto(
      id: mediaId,
      status: 'ready',
      type: 'image',
      cdnUrl: 'https://cdn.example/media/$mediaId',
    );
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectAutoVideoCover({
    required String mediaId,
  }) async {
    return ContentVideoCoverSelectionWireDto(
      mediaId: mediaId,
      coverStrategy: 'first_frame',
    );
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) async {
    return ContentVideoCoverSelectionWireDto(
      mediaId: mediaId,
      coverStrategy: 'manual',
      manualCoverAssetId: coverAssetId,
    );
  }

  @override
  Future<ContentArticleSummaryGenerateResponseDto> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    final preview = body.length > 100 ? body.substring(0, 100) : body;
    return ContentArticleSummaryGenerateResponseDto(summary: '$title：$preview');
  }

  @override
  Future<ContentRecommendationResponseDto> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ContentRecommendationResponseDto(items: <Map<String, dynamic>>[]);
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final filtered = _allDiscoveryPosts()
        .where((p) => p.authorId == userId)
        .where(
          (p) => _matchesIdentityAndTypePost(p, identity: identity, type: type),
        )
        .toList();
    return CursorPage<PostBaseDto>(items: filtered, nextCursor: null);
  }

  List<PostBaseDto> _allDiscoveryPosts() {
    final seeded = _seedPosts;
    if (seeded != null) {
      return List<PostBaseDto>.from(seeded, growable: false);
    }
    return _discoverySeedPosts();
  }

  List<PostBaseDto> _resolveDiscoveryPosts({
    required String category,
    String? identity,
    String? type,
  }) {
    final resolvedIdentity = identity ?? _mapCategoryToIdentity(category);
    final resolvedType = _normalizeFeedType(
      type ?? _mapCategoryToFeedType(category),
    );
    return _allDiscoveryPosts()
        .where(
          (item) => _matchesIdentityAndTypePost(
            item,
            identity: resolvedIdentity,
            type: resolvedType,
          ),
        )
        .toList(growable: false);
  }

  bool _matchesIdentityAndTypePost(
    PostBaseDto post, {
    String? identity,
    String? type,
  }) {
    return _matchesIdentityAndType(
      <String, dynamic>{
        'contentType': post.type,
        'type': post.type,
        'contentIdentity': post.identity,
        'identity': post.identity,
      },
      identity: identity,
      type: type,
    );
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

  String? _mapCategoryToFeedType(String category) {
    final mapped =
        GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
    return _normalizeFeedType(mapped);
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

  bool _matchesIdentityAndType(
    Map<String, dynamic> item, {
    String? identity,
    String? type,
  }) {
    final itemType = _normalizeFeedType(
      item['contentType']?.toString() ?? item['type']?.toString(),
    );
    final itemIdentity =
        (item['contentIdentity'] ??
                item['identity'] ??
                ((itemType == 'micro' || item['type']?.toString() == 'moment')
                    ? 'moment'
                    : 'work'))
            .toString();
    final expectedIdentity = (identity ?? '').trim();
    final expectedType = _normalizeFeedType(type);
    if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
      return false;
    }
    if (expectedType != null && expectedType.isNotEmpty) {
      if (expectedType == 'moment') {
        return itemIdentity == 'moment';
      }
      return itemType == expectedType;
    }
    return true;
  }

  String _mockCategoryForCircleIds(Iterable<String> circleIds) {
    for (final circleId in circleIds) {
      switch (circleId) {
        case 'circle_photo_01':
        case 'c1':
        case 'c-human-1':
        case 'c-photo-owner':
          return 'humanity';
        case 'c2':
          return 'travel';
        case 'c-tech-admin':
          return 'tech';
        case 'c-meet-1':
        case 'c-meet-2':
          return 'meet';
        case 'c-car-2':
          return 'car';
      }
    }
    return '';
  }

  @override
  bool get requiresResolvedPersonaForMutations => false;

  @override
  bool get usesEmbeddedContentCatalog => true;

  @override
  bool get usesCloudAssistantEdgeSync => false;

  @override
  Map<String, dynamic>? discoveryPresentationWireForPost(String postId) {
    return lookupCanonicalDiscoveryWireRowByPostId(postId);
  }

  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() {
    return ContentMockData.discoveryArticleData
        .map((e) => postBaseDtoFromMap(e.toDiscoveryWireMap()))
        .where((p) => p.isArticleLike)
        .toList(growable: false);
  }
}
