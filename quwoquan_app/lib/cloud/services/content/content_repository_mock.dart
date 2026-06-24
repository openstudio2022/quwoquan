part of 'content_repository.dart';

class MockContentRepository implements ContentRepository {
  MockContentRepository({List<PostBaseDto>? seedPosts})
    : _seedPosts = seedPosts ?? _contractSeedPosts();

  final List<PostBaseDto>? _seedPosts;

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
  int countersStubShareCount = 0;

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
    final items = await _resolveDiscoveryPosts(
      category: category,
      identity: identity,
      type: type,
    );
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, items.length);
    final safeLimit = limit <= 0 ? items.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, items.length);
    final pageItems = items
        .sublist(safeOffset, end)
        .map(_withLiveCommentCount)
        .toList(growable: false);
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
        lookupCanonicalDiscoveryWireRowByPostId(postId) ??
        await _alphaShowcasePostWireById(postId) ??
        _profilePreviewPostWireById(postId);
    if (raw == null) {
      _throwMockPostNotFound(postId);
    }
    return ContentPostDetailPayload.fromWire(_withLiveCommentCountWire(raw));
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
    final resolvedPostId = _resolveSeededCommentPostId(postId);
    final all = commentsStub
        .where(
          (comment) =>
              comment.postId == resolvedPostId &&
              comment.status != 'deleted' &&
              (comment.parentCommentId == null ||
                  comment.parentCommentId!.isEmpty) &&
              (comment.replyToCommentId == null ||
                  comment.replyToCommentId!.isEmpty),
        )
        .toList(growable: false);
    final sorted = _sortComments(all, sort);
    // 计数单一真相源：与 getPost/getCounters 同走 _liveCommentCountForPost
    // （排除软删），保证三者与 currentTotal 恒一致。
    final totalCount = _liveCommentCountForPost(resolvedPostId);
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, sorted.length);
    final safeLimit = limit <= 0 ? sorted.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, sorted.length);
    final page = sorted
        .sublist(safeOffset, end)
        .map((comment) => _withReplyPreview(resolvedPostId, comment))
        .toList(growable: false);
    return CommentPage(
      items: page,
      nextCursor: end < sorted.length ? '$end' : null,
      totalCount: totalCount,
    );
  }

  @override
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = CloudApiQueryDefaults.commentRepliesLimit,
  }) async {
    final resolvedPostId = _resolveSeededCommentPostId(postId);
    final replies =
        commentsStub
            .where(
              (comment) =>
                  comment.postId == resolvedPostId &&
                  comment.parentCommentId == commentId &&
                  comment.status != 'deleted',
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
      totalCount: replies.length,
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
      'postId': _resolveSeededCommentPostId(postId),
      'content': content,
      'authorId': 'mock_user',
      'subAccountId': subAccountId ?? 'mock_user',
      // 云侧 personaContextVersion 为 int64（handler 经 asInt64Flexible 收敛），
      // 响应回显为数字。mock 必须与远端 wire 形态一致，避免 CommentDto.fromMap
      // 把字符串当作 num 解析时崩溃（alpha 评论提交不可用的根因）。
      'personaContextVersion': _personaContextVersionToInt(
        personaContextVersion,
      ),
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
    return dto;
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    // 软删墓碑（与云侧一致）：保留评论并打 status=deleted + deletedAt，
    // 使 _liveCommentCountForPost 自然剔除、listComments 不再展示，且
    // getCommentCountsDelta 能在区间内统计到该删除，支撑可解释增量。
    commentsStub = commentsStub
        .map(
          (c) => c.id == commentId
              ? c.copyWith(
                  status: 'deleted',
                  deletedAt: () => c.deletedAt ?? DateTime.now(),
                )
              : c,
        )
        .toList(growable: false);
  }

  @override
  Future<CommentCountsDelta> getCommentCountsDelta({
    required String postId,
    DateTime? since,
  }) async {
    final resolvedPostId = _resolveSeededCommentPostId(postId);
    // watermark = 本次查询时刻（作下次 since 基线，保证相邻 delta 不重不漏）。
    final watermark = DateTime.now();
    var created = 0;
    var deleted = 0;
    for (final comment in commentsStub) {
      if (comment.postId != resolvedPostId) {
        continue;
      }
      // createdSinceCount：createdAt ∈ (since, watermark]（不论其后是否被删）。
      if (_withinHalfOpenWindow(comment.createdAt, since, watermark)) {
        created++;
      }
      // deletedSinceCount：status=deleted 且 deletedAt ∈ (since, watermark]。
      if (comment.status == 'deleted') {
        final deletedAt = comment.deletedAt;
        if (deletedAt != null &&
            _withinHalfOpenWindow(deletedAt, since, watermark)) {
          deleted++;
        }
      }
    }
    return CommentCountsDelta(
      createdSinceCount: created,
      deletedSinceCount: deleted,
      currentTotal: _liveCommentCountForPost(resolvedPostId),
      watermark: watermark,
      since: since,
    );
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
  Future<CommentDto> setCommentPinned({
    required String postId,
    required String commentId,
    required bool pinned,
  }) async {
    CommentDto? updated;
    commentsStub = commentsStub
        .map((comment) {
          if (comment.id != commentId) {
            return comment;
          }
          updated = comment.copyWith(
            isPinned: pinned,
            pinnedAt: () => pinned ? DateTime.now() : null,
          );
          return updated!;
        })
        .toList(growable: false);
    // 与云侧一致：置顶的一级评论排在最前（保持其余评论的相对顺序）。
    final pinnedFirst = commentsStub.where((c) => c.isPinned).toList();
    final rest = commentsStub.where((c) => !c.isPinned).toList();
    commentsStub = [...pinnedFirst, ...rest];
    return updated ??
        CommentDto(
          id: commentId,
          postId: postId,
          authorId: '',
          content: '',
          isPinned: pinned,
          pinnedAt: pinned ? DateTime.now() : null,
          createdAt: DateTime.now(),
        );
  }

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null, totalCount: 0);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null, totalCount: 0);
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
      commentCount: _liveCommentCountForPost(postId),
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
    String assetScope = 'draft',
  }) async {
    final ts = DateTime.now().millisecondsSinceEpoch;
    final normalizedType = mediaType.trim() == 'video' ? 'video' : 'image';
    final ext = normalizedType == 'video' ? 'mp4' : 'jpg';
    final sessionId = 'mock_upload_${normalizedType}_$ts';
    final mediaId = 'mock_media_${normalizedType}_$ts';
    final uploadObjectKey =
        'upload/media/user/mock/$assetScope/post/mock_user/$sessionId/$mediaId/original.$ext';
    final uploadUrl =
        '${CloudRuntimeConfig.mediaUploadBaseUrl}/$uploadObjectKey';
    return ContentMediaInitUploadResponseDto(
      sessionId: sessionId,
      mediaId: mediaId,
      uploadUrl: uploadUrl,
      presignUrl: uploadUrl,
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    final isVideo = sessionId.contains('video');
    final objectKey =
        'media/user/mock/draft/post/mock_user/$sessionId/mock_media_$sessionId/original.${isVideo ? 'mp4' : 'jpg'}';
    return ContentMediaCompleteUploadResponseDto(
      sessionId: sessionId,
      status: 'ready',
      cdnUrl:
          '${isVideo ? CloudRuntimeConfig.mediaVideoCdnBaseUrl : CloudRuntimeConfig.mediaImageCdnBaseUrl}/$objectKey',
      assetId: 'mock_media_$sessionId',
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {}

  @override
  Future<void> bindMediaAssetsToPost({
    required String postId,
    required List<String> assetIds,
  }) async {}

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
    final coverUrl =
        '${CloudRuntimeConfig.mediaImageCdnBaseUrl}/media/user/mock/draft/post/mock_user/mock_session/$mediaId/cover.jpg';
    return ContentVideoCoverSelectionWireDto(
      mediaId: mediaId,
      coverStrategy: 'first_frame',
      thumbnailUrl: coverUrl,
      coverUrl: coverUrl,
      coverFrameTimeMs: 0,
    );
  }

  @override
  Future<ContentVideoCoverSelectionWireDto> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
    int coverFrameTimeMs = 0,
  }) async {
    final coverUrl =
        '${CloudRuntimeConfig.mediaImageCdnBaseUrl}/media/user/mock/draft/post/mock_user/mock_session/$coverAssetId/original.jpg';
    return ContentVideoCoverSelectionWireDto(
      mediaId: mediaId,
      coverStrategy: 'manual',
      manualCoverAssetId: coverAssetId,
      thumbnailUrl: coverUrl,
      coverUrl: coverUrl,
      coverFrameTimeMs: coverFrameTimeMs,
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
    final authorId = userId.trim();
    final directPosts = _allDiscoveryPosts()
        .where((p) => p.authorId == authorId)
        .toList(growable: false);
    final sourcePosts = _mergePostSeeds(
      directPosts,
      _profilePreviewPostsFor(authorId),
    );
    final filtered = sourcePosts
        .where(
          (p) => _matchesIdentityAndTypePost(p, identity: identity, type: type),
        )
        .toList();
    return CursorPage<PostBaseDto>(items: filtered, nextCursor: null);
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
