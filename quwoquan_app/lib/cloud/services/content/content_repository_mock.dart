part of 'content_repository.dart';

class MockContentRepository
    implements
        ContentReadRepository,
        ContentPostDetailReader,
        ContentAuthorPostsReader,
        ContentPostSearchRepository,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository {
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

  /// 软删除墓碑：被 [deletePost] 删除的帖 id。删除后 [getPost] 抛「不存在」，
  /// 与云侧软删 + tombstone 语义一致，使删除旅程在 alpha 下可契约验证（R12/R13）。
  final Set<String> _deletedPostIds = <String>{};

  int countersStubLikeCount = 0;

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
    final pageItems = items.sublist(safeOffset, end).toList(growable: false);
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
    return ContentPostDetailPayload.fromWire(raw);
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
      commentCount: 0,
      shareCount: 0,
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
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
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
