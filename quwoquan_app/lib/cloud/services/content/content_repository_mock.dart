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
    if (contractPosts.isEmpty) {
      return null;
    }
    return _mergePostSeeds(contractPosts, _discoverySeedPosts());
  }

  static List<PostBaseDto> _discoverySeedPosts() {
    return aggregateDiscoveryWireSlices(
      showcase: ContentMockData.seededShowcaseFeedItems,
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

  Never _throwMockPostNotFound(String postId) {
    throw CloudErrorMapper.fromStatusCode(
      404,
      body:
          '{"code":"${ContentErrorCode.postNotFound.code}","userMessage":"${ContentErrorMessages.zh[ContentErrorCode.postNotFound]}"}',
      requestPath: ContentApiMetadata.getPostPath(postId: postId),
    );
  }

  Exception? throwOnLike;
  Exception? throwOnCreateComment;
  Exception? throwOnShare;

  /// 软删除墓碑：被 [deletePost] 删除的帖 id。删除后 [getPost] 抛「不存在」，
  /// 与云侧软删 + tombstone 语义一致，使删除旅程在 alpha 下可契约验证（R12/R13）。
  final Set<String> _deletedPostIds = <String>{};

  int likePostCallCount = 0;
  int createCommentCallCount = 0;
  int sharePostCallCount = 0;
  String? lastCommentText;
  String? lastCommentPostId;

  Map<String, dynamic> reactionStateStub = {'liked': false, 'shared': false};
  List<CommentDto> commentsStub = _contractSeedComments();
  int countersStubLikeCount = 0;
  int countersStubCommentCount = 0;
  int countersStubShareCount = 0;

  static List<CommentDto> _contractSeedComments() {
    final comments = <CommentDto>[];
    for (final ref in const <String>[
      'content_discovery_core',
      'comment_thread_v2_core',
    ]) {
      final seed = ContractFixtureRuntimeLoader.contentSeedSet(ref);
      final raw = seed?['comments'];
      if (raw is! List) {
        continue;
      }
      comments.addAll(
        raw.whereType<Map>().map(
          (item) => CommentDto.fromMap(item.cast<String, dynamic>()),
        ),
      );
    }
    final byId = <String, CommentDto>{};
    for (final comment in comments) {
      byId[comment.id] = comment;
    }
    return byId.values.toList(growable: false);
  }

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
      'authorAvatarUrl':
          'media/avatar/s/archived-avatar/content/default/v1/avatar.jpg',
      'body': '',
      'mediaUrls': <String>[],
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
      'createdAt': DateTime.now().toUtc().toIso8601String(),
      'assistantUsePolicy': 'inherit',
      ...payloadMerge,
    };
    final contentType = (merged['contentType'] ?? merged['type'] ?? 'micro')
        .toString();
    merged['contentType'] = contentType;
    if (contentType == 'micro') {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'moment';
      merged['identity'] = merged['identity'] ?? 'moment';
    } else {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'work';
      merged['identity'] = merged['identity'] ?? 'work';
    }
    return merged;
  }

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
    final items = _resolveDiscoveryPosts(
      category: category,
      identity: identity,
      type: type,
    );
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, items.length);
    final safeLimit = limit <= 0 ? items.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, items.length);
    final pageItems = items.sublist(safeOffset, end);
    final nextCursor = end < items.length ? '$end' : null;
    // 模拟服务端权威下发：首刷生成 frq_ 归因 id，分页回显客户端透传的同一 id。
    final resolvedFeedRequestId = (feedRequestId?.trim().isNotEmpty == true)
        ? feedRequestId!.trim()
        : 'frq_mock_${DateTime.now().microsecondsSinceEpoch}';
    return DiscoveryFeedPage(
      items: pageItems,
      nextCursor: nextCursor,
      feedRequestId: resolvedFeedRequestId,
      rankingVersion: 'rec-mock',
      reasonVersion: 'reason-mock',
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
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _searchMockPosts(
    query: query,
    identity: identity,
    type: type,
    categoryId: categoryId,
    subCategory: subCategory,
    limit: limit,
  );

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    if (_deletedPostIds.contains(postId)) {
      _throwMockPostNotFound(postId);
    }
    final raw =
        _contractSeedPostWire(postId) ??
        lookupCanonicalDiscoveryWireRowByPostId(postId);
    if (raw == null) {
      _throwMockPostNotFound(postId);
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
    String sort = 'recommended',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final all = commentsStub
        .where(
          (comment) =>
              comment.postId == postId &&
              (comment.parentCommentId == null ||
                  comment.parentCommentId!.isEmpty) &&
              (comment.replyToCommentId == null ||
                  comment.replyToCommentId!.isEmpty),
        )
        .toList(growable: false);
    final sorted = _sortComments(all, sort);
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, sorted.length);
    final safeLimit = limit <= 0 ? sorted.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, sorted.length);
    return CommentPage(
      items: sorted.sublist(safeOffset, end),
      nextCursor: end < sorted.length ? '$end' : null,
    );
  }

  @override
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = CloudApiQueryDefaults.commentRepliesLimit,
  }) async {
    final replies =
        commentsStub
            .where(
              (comment) =>
                  comment.postId == postId &&
                  comment.parentCommentId == commentId,
            )
            .toList(growable: false)
          ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, replies.length);
    final safeLimit = limit <= 0 ? replies.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, replies.length);
    return CommentPage(
      items: replies.sublist(safeOffset, end),
      nextCursor: end < replies.length ? '$end' : null,
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
      'attachmentMediaIds': attachmentMediaIds,
      'attachments': attachmentMediaIds
          .map(
            (id) => <String, dynamic>{
              'mediaId': id,
              'type': 'image',
              'url': 'media/comment/$id/v1/comment.png',
              'thumbnailUrl': 'media/comment/$id/v1/thumb.png',
              'moderationStatus': 'approved',
            },
          )
          .toList(growable: false),
      'mentions': mentions,
      'likeCount': 0,
      'dislikeCount': 0,
      'viewerReaction': 'none',
      'status': 'visible',
      'isAuthor': false,
      'canDelete': true,
      'canReply': true,
      'canReport': false,
      'createdAt': DateTime.now().toIso8601String(),
    };
    if (replyToCommentId != null) {
      comment['replyToCommentId'] = replyToCommentId;
      final target = commentsStub.where((c) => c.id == replyToCommentId);
      final parent = target.isEmpty
          ? replyToCommentId
          : (target.first.parentCommentId?.isNotEmpty == true
                ? target.first.parentCommentId
                : target.first.id);
      comment['parentCommentId'] = parent;
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
  Future<CommentDto> reactToComment({
    required String commentId,
    required String reaction,
  }) async {
    CommentDto? updated;
    commentsStub = commentsStub
        .map((comment) {
          if (comment.id != commentId) {
            return comment;
          }
          final current = comment.viewerReaction;
          var likeCount = comment.likeCount;
          var dislikeCount = comment.dislikeCount;
          if (current == 'like') {
            likeCount = (likeCount - 1).clamp(0, 1 << 31).toInt();
          }
          if (current == 'dislike') {
            dislikeCount = (dislikeCount - 1).clamp(0, 1 << 31).toInt();
          }
          if (reaction == 'like') likeCount++;
          if (reaction == 'dislike') dislikeCount++;
          updated = comment.copyWith(
            likeCount: likeCount,
            dislikeCount: dislikeCount,
            viewerReaction: reaction,
          );
          return updated!;
        })
        .toList(growable: false);
    return updated ??
        CommentDto(
          id: commentId,
          postId: '',
          authorId: '',
          content: '',
          viewerReaction: reaction,
          createdAt: DateTime.now(),
        );
  }

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
          'reply_preview_count': 1,
          'reply_expand_page_size': 10,
          'fold_line_count': 3,
          'sort': {'default': 'recommended'},
          'attachment': {'max_images': 1},
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
  Future<void> deletePost({required String postId}) async {
    if (postId.trim().isEmpty) {
      return;
    }
    _deletedPostIds.add(postId);
  }

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
    final uploadObjectKey =
        'upload/media/user/mock/draft/post/mock_user/mock_upload_$ts/mock_media_$ts/original.jpg';
    final uploadUrl =
        '${CloudRuntimeConfig.mediaUploadBaseUrl}/$uploadObjectKey';
    return ContentMediaInitUploadResponseDto(
      sessionId: 'mock_upload_$ts',
      mediaId: 'mock_media_$ts',
      uploadUrl: uploadUrl,
      presignUrl: uploadUrl,
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    final objectKey =
        'media/user/mock/draft/post/mock_user/$sessionId/mock_media_$sessionId/original.jpg';
    return ContentMediaCompleteUploadResponseDto(
      sessionId: sessionId,
      status: 'ready',
      cdnUrl: '${CloudRuntimeConfig.mediaImageCdnBaseUrl}/$objectKey',
      assetId: 'mock_media_$sessionId',
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {}

  @override
  Future<ContentMediaAssetWireDto> getMediaAsset({
    required String mediaId,
  }) async {
    final objectKey =
        'media/user/mock/draft/post/mock_user/mock_session/$mediaId/original.jpg';
    return ContentMediaAssetWireDto(
      id: mediaId,
      status: 'ready',
      type: 'image',
      cdnUrl: '${CloudRuntimeConfig.mediaImageCdnBaseUrl}/$objectKey',
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

  Map<String, dynamic>? _contractSeedPostWire(String postId) {
    final trimmed = postId.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final raw = ContractFixtureRuntimeLoader.contentSeedSet()?['posts'];
    if (raw is! List) {
      return null;
    }
    for (final item in raw.whereType<Map>()) {
      final wire = item.cast<String, dynamic>();
      final itemId =
          wire['postId']?.toString() ??
          wire['_id']?.toString() ??
          wire['id']?.toString() ??
          '';
      if (itemId == trimmed) {
        return Map<String, dynamic>.from(wire);
      }
    }
    return null;
  }

  List<CommentDto> _sortComments(List<CommentDto> comments, String sort) {
    final sorted = List<CommentDto>.from(comments);
    switch (sort) {
      case 'latest':
        sorted.sort((a, b) => b.createdAt.compareTo(a.createdAt));
        break;
      case 'most_liked':
        sorted.sort((a, b) {
          final byLike = b.likeCount.compareTo(a.likeCount);
          return byLike != 0 ? byLike : b.createdAt.compareTo(a.createdAt);
        });
        break;
      case 'recommended':
      default:
        sorted.sort((a, b) {
          final byScore = (b.recommendedScore ?? 0).compareTo(
            a.recommendedScore ?? 0,
          );
          return byScore != 0 ? byScore : b.createdAt.compareTo(a.createdAt);
        });
        break;
    }
    return sorted;
  }

  List<PostBaseDto> _resolveDiscoveryPosts({
    required String category,
    String? identity,
    String? type,
  }) {
    final requestedIdentity = (identity ?? '').trim();
    final requestedType = _normalizeFeedType(type);
    if (_shouldServeAlphaShowcaseFeed(
      category: category,
      requestedIdentity: requestedIdentity,
      requestedType: requestedType,
    )) {
      return _alphaShowcasePosts();
    }
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

  List<PostBaseDto> _alphaShowcasePosts() {
    return ContentMockData.seededShowcaseFeedItems
        .map((item) => postBaseDtoFromMap(item.toDiscoveryWireMap()))
        .toList(growable: false);
  }

  bool _shouldServeAlphaShowcaseFeed({
    required String category,
    required String requestedIdentity,
    required String? requestedType,
  }) {
    if (requestedType != null) return false;
    switch (category.trim()) {
      case 'recommend':
      case 'recommended':
        return requestedIdentity.isEmpty || requestedIdentity == 'moment';
      case 'micro':
      case 'moment':
        return requestedIdentity == 'moment';
      default:
        return false;
    }
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
                (itemType == 'micro' ? 'moment' : 'work'))
            .toString();
    final expectedIdentity = (identity ?? '').trim();
    final expectedType = _normalizeFeedType(type);
    if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
      return false;
    }
    if (expectedType != null && expectedType.isNotEmpty) {
      return itemType == expectedType;
    }
    return true;
  }

  String _mockCategoryForCircleIds(Iterable<String> circleIds) {
    for (final circleId in circleIds) {
      switch (circleId) {
        case 'fixture_circle_photo':
        case 'circle_photo_01':
        case 'c1':
        case 'c-human-1':
        case 'c-photo-owner':
        case 'c-meet-2':
          return 'photography';
        case 'c2':
        case 'c3':
          return 'travel';
        case 'c-tech-admin':
          return 'tech';
        case 'c-meet-1':
          return 'campus';
        case 'c-car-1':
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
  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId) {
    return DiscoveryPresentationWire.fromRow(
      lookupCanonicalDiscoveryWireRowByPostId(postId),
    );
  }

  @override
  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix() {
    return ContentMockData.discoveryArticleData
        .map((e) => postBaseDtoFromMap(e.toDiscoveryWireMap()))
        .where((p) => p.isArticleLike)
        .toList(growable: false);
  }
}
