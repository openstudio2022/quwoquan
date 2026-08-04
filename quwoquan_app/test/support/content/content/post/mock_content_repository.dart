/// 测试专用 content 聚合替身（原 lib/cloud/services/content 三个 mock part 迁入）。
///
/// 生产组合根为 Remote-only；本文件只服务 local_contract，不得进入 Patrol/UAT
/// 装配（R15 物理隔离）。
library;

import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/domain/discovery_feed_page.dart';
import 'package:quwoquan_app/content/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/content/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../cloud_services/object_doubles/object_scenario_seed_reader.dart';
import 'content_mock_data.dart';
import 'test_content_app_config.dart';
// ── 发现区 wire 聚合与查找（原 lib discovery_wire_lookup.dart，仅测试消费）──

/// 将四类发现区 [ContentPostViewData] 列表合并为单行扫描序列（与 [ContentMockData] 对齐）。
List<Map<String, dynamic>> aggregateDiscoveryWireSlices({
  required List<ContentPostViewData> photo,
  required List<ContentPostViewData> video,
  required List<ContentPostViewData> article,
  required List<ContentPostViewData> moment,
  List<ContentPostViewData> showcase = const <ContentPostViewData>[],
}) {
  return <Map<String, dynamic>>[
    ...showcase.map(_mockReadModelMapFromViewData),
    ...photo.map(_mockReadModelMapFromViewData),
    ...video.map(_mockReadModelMapFromViewData),
    ...article.map(_mockReadModelMapFromViewData),
    ...moment.map(_mockReadModelMapFromViewData),
  ];
}

Map<String, dynamic> _mockReadModelMapFromViewData(ContentPostViewData post) {
  return Map<String, dynamic>.from(
    contentPostProjectionFromViewData(post).toWire(),
  );
}

ContentPostDetailSlice _mockDetailSliceFromReadModelMap(
  Map<String, dynamic> raw,
) {
  final projection = contentPostProjectionFromReadModelMap(raw);
  final manifestRaw = raw['articleAssetManifest'];
  final renderProfileRaw = raw['articleRenderProfile'];
  final createdAt =
      projection.createdAt ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  return ContentPostDetailSlice(
    postId: projection.postId,
    contentType: projection.contentType,
    contentIdentity: projection.contentIdentity,
    assistantUsePolicy: projection.assistantUsePolicy,
    authorId: projection.authorId,
    authorDisplayName: projection.authorDisplayName,
    authorAvatarUrl: projection.authorAvatarUrl,
    title: projection.title,
    body: projection.body,
    summary: projection.summary,
    mediaAssetIds: projection.mediaAssetId == null
        ? null
        : <String>[projection.mediaAssetId!],
    mediaUrls: projection.mediaUrls,
    coverUrl: projection.coverUrl,
    thumbnailUrl: projection.thumbnailUrl,
    videoUrl: projection.videoUrl,
    width: projection.width,
    height: projection.height,
    durationMs: projection.durationMs,
    articleMarkdown: raw['articleMarkdown']?.toString(),
    markdownDialect: raw['markdownDialect']?.toString(),
    articleMarkdownDigest: raw['articleMarkdownDigest']?.toString(),
    articleAssetManifest: manifestRaw is Map
        ? PostArticleAssetManifest.fromWire(
            Map<String, Object?>.from(manifestRaw),
            'MockContentRepository.articleAssetManifest',
          )
        : null,
    articleRenderProfile: renderProfileRaw is Map
        ? PostArticleRenderProfile.fromWire(
            Map<String, Object?>.from(renderProfileRaw),
            'MockContentRepository.articleRenderProfile',
          )
        : null,
    contentVertical: projection.contentVertical,
    articleTemplate: projection.articleTemplate,
    articleFontPreset: projection.articleFontPreset,
    status: raw['status']?.toString() ?? 'published',
    visibility: raw['visibility']?.toString() ?? 'public',
    likeCount: projection.likeCount,
    commentCount: projection.commentCount,
    shareCount: projection.shareCount,
    viewCount: raw['viewCount'] is num ? (raw['viewCount'] as num).toInt() : 0,
    createdAt: createdAt,
    updatedAt: projection.updatedAt ?? createdAt,
    publishedAt: projection.publishedAt,
  );
}

/// 在已聚合的公共 wire 行中按帖子 id 查找。
Map<String, dynamic>? findDiscoveryWireRowByPostId(
  String postId,
  List<Map<String, dynamic>> aggregatedRows,
) {
  if (postId.isEmpty) return null;
  for (final item in aggregatedRows) {
    final itemId = item['postId']?.toString() ?? '';
    if (itemId == postId) {
      return item;
    }
  }
  return null;
}

/// Canonical mock 发现区行查找：仅由 [MockContentRepository] 与测试持有。
Map<String, dynamic>? lookupCanonicalDiscoveryWireRowByPostId(String postId) {
  final row = findDiscoveryWireRowByPostId(
    postId,
    aggregateDiscoveryWireSlices(
      photo: ContentMockData.discoveryPhotoData,
      video: ContentMockData.discoveryVideoData,
      article: ContentMockData.discoveryArticleData,
      moment: ContentMockData.discoveryMomentData,
      showcase: ContentMockData.seededShowcaseFeedItems,
    ),
  );
  if ((row?['contentType']?.toString() ?? '') == 'article') {
    return ContentMockData.articleWireByPostId(postId) ?? row;
  }
  return row;
}

// ── 帖子种子合成 ─────────────────────────────────────────────────────────

const String _mockContentDefaultAuthorAvatarUrl =
    'media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png';

List<ContentPostViewData>? _contractSeedPosts() {
  final seed = objectScenarioSeedReader.contentSeedSet();
  final posts = seed?['posts'];
  final contractPosts = <ContentPostViewData>[];
  if (posts is! List) {
    return null;
  }
  contractPosts.addAll(
    posts
        .whereType<Map>()
        .map(
          (item) =>
              contentPostViewDataFromReadModelMap(item.cast<String, dynamic>()),
        )
        .toList(growable: false),
  );
  if (contractPosts.isEmpty) {
    return null;
  }
  return _mergePostSeeds(contractPosts, _discoverySeedPosts());
}

List<ContentPostViewData> _discoverySeedPosts() {
  return aggregateDiscoveryWireSlices(
    showcase: ContentMockData.seededShowcaseFeedItems,
    photo: ContentMockData.discoveryPhotoData,
    video: ContentMockData.discoveryVideoData,
    moment: ContentMockData.discoveryMomentData,
    article: ContentMockData.discoveryArticleData,
  ).map(contentPostViewDataFromReadModelMap).toList(growable: false);
}

List<ContentPostViewData> _mergePostSeeds(
  List<ContentPostViewData> primary,
  List<ContentPostViewData> fallback,
) {
  final byId = <String, ContentPostViewData>{};
  for (final post in primary) {
    byId[post.id] = post;
  }
  for (final post in fallback) {
    byId.putIfAbsent(post.id, () => post);
  }
  return byId.values.toList(growable: false);
}

// ── 聚合替身本体 ─────────────────────────────────────────────────────────

class MockContentRepository
    implements
        ContentReadRepository,
        ContentPostDetailReader,
        ContentAuthorPostsReader,
        ContentPostDeleteCommandWriter,
        ContentConfigRepository {
  MockContentRepository({List<ContentPostViewData>? seedPosts})
    : _seedPosts = seedPosts ?? _contractSeedPosts();

  final List<ContentPostViewData>? _seedPosts;

  Never _throwMockPostNotFound(String postId) {
    throw CloudErrorMapper.fromStatusCode(
      404,
      body:
          '{"code":"${ContentErrorCode.postNotFound.code}","userMessage":"${ContentErrorMessages.zh[ContentErrorCode.postNotFound]}"}',
      requestPath: ContentApiMetadata.getPostPath(postId: postId),
    );
  }

  Never _throwMockContentDeleted(String postId) {
    throw CloudErrorMapper.fromStatusCode(
      410,
      body:
          '{"code":"${ContentErrorCode.contentDeleted.code}","userMessage":"${ContentErrorMessages.zh[ContentErrorCode.contentDeleted]}"}',
      requestPath: ContentApiMetadata.getPostPath(postId: postId),
    );
  }

  /// 软删除墓碑：保留期内 [getPost] 返回 410 content_deleted；未知 id 仍为 404。
  /// 该分流与云侧 DeletedPostTombstone 契约同源，使删除旅程可验证（R12/R13）。
  final Set<String> _deletedPostIds = <String>{};

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
    cancellation?.throwIfCancelled();
    // 与 Remote 一致：channelId 非空即频道推荐主链路，identity/type 不参与过滤。
    final resolvedChannelId = channelId?.trim() ?? '';
    final channelRouted = resolvedChannelId.isNotEmpty;
    // N2-4 premium fail-closed 同构：精品流只允许精品池供给（云侧
    // GatePremiumStreamSource：池空返回空列表，绝不回填全量时间流）。
    // 池成员唯一 seed 真相源是 home_feed_core.featuredFeedPostIds（与云侧
    // rm_premium_pool 物化集合同构、与 alpha runner adapter 同判定），
    // supplySource==data_engineering 供给兜底（策展池外的数据工程直供）。
    List<ContentPostViewData> items;
    if (channelRouted &&
        (resolvedChannelId == 'premium' ||
            resolvedChannelId == 'premium_stream')) {
      final pool = _premiumPoolPostIds();
      items = (await _resolveDiscoveryPosts(category: 'recommend'))
          .where(
            (item) =>
                pool.contains(item.id) ||
                item.supplySource == 'data_engineering',
          )
          .toList(growable: false);
    } else if (channelRouted && resolvedChannelId == 'travel') {
      // travel 垂类同构：镜像云侧 postMatchesVertical（contentVertical 优先，
      // 关键词兜底），不混入非旅行内容。
      items = (await _resolveDiscoveryPosts(
        category: 'recommend',
      )).where(_matchesTravelVerticalPost).toList(growable: false);
    } else {
      items = await _resolveDiscoveryPosts(
        category: channelRouted ? resolvedChannelId : category,
        identity: channelRouted ? null : identity,
        type: channelRouted ? null : type,
      );
    }
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
    cancellation?.throwIfCancelled();
    return DiscoveryFeedPage(
      items: pageItems,
      nextCursor: nextCursor,
      feedRequestId: resolvedFeedRequestId,
      policyDigest:
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      // N2-4 objectCards 同构：首刷（无 cursor）+ 频道推荐主链路注入实体主页卡，
      // 形状与云侧 resolveObjectCards（everyN 锚点 + entity_homepage）一致，
      // 使 Widget 层混排/埋点契约可在 local_contract 验证。
      objectCards: _mockObjectCards(
        channelRouted: channelRouted,
        channelId: resolvedChannelId,
        cursor: cursor,
        itemCount: pageItems.length,
      ),
    );
  }

  /// 与云侧 policy（everyN=8、maxCards≤3、entity_homepage only）同构的对象卡。
  List<FeedObjectCard> _mockObjectCards({
    required bool channelRouted,
    required String channelId,
    required String? cursor,
    required int itemCount,
  }) {
    const everyN = 8;
    if (!channelRouted || channelId != 'recommend') {
      return const <FeedObjectCard>[];
    }
    if ((cursor ?? '').trim().isNotEmpty) {
      return const <FeedObjectCard>[];
    }
    if (itemCount < everyN) {
      return const <FeedObjectCard>[];
    }
    return <FeedObjectCard>[
      FeedObjectCard(
        objectKind: 'entity_homepage',
        objectId: 'homepage_sight_west_lake',
        title: '西湖',
        subtitle: '杭州 · 风景名胜',
        tagRefs: const <String>['Topic/旅行/杭州'],
        reasonText: 'affinity',
        recallPath: 'entity_affinity_card',
        anchorIndex: everyN,
      ),
    ];
  }

  /// 精品池成员（home_feed_core.featuredFeedPostIds，env-seed-first 唯一池 seed）。
  Set<String> _premiumPoolPostIds() {
    final raw = objectScenarioSeedReader.contentSeedSet(
      'home_feed_core',
    )?['featuredFeedPostIds'];
    if (raw is! List) {
      return const <String>{};
    }
    return raw
        .map((item) => item.toString().trim())
        .where((id) => id.isNotEmpty)
        .toSet();
  }

  /// 镜像云侧 postMatchesVertical 的 travel 判定（contentVertical 优先，关键词兜底）。
  bool _matchesTravelVerticalPost(ContentPostViewData item) {
    final vertical = (item.contentVertical ?? '').trim();
    if (vertical.isNotEmpty) {
      return vertical == 'travel_photography';
    }
    const keywords = <String>['旅行', '旅游', '出行', '风景', '打卡', 'travel'];
    final haystack = '${item.title} ${item.body ?? ''}';
    return keywords.any(haystack.contains);
  }

  @override
  Future<List<ContentPostViewData>> listDiscoveryFeed({
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
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    if (_deletedPostIds.contains(postId)) {
      _throwMockContentDeleted(postId);
    }
    final raw =
        _contractSeedPostWire(postId) ??
        lookupCanonicalDiscoveryWireRowByPostId(postId) ??
        await _alphaShowcasePostWireById(postId) ??
        _profilePreviewPostWireById(postId);
    if (raw == null) {
      _throwMockPostNotFound(postId);
    }
    return ContentPostDetailPayload.fromWire(
      _mockDetailSliceFromReadModelMap(raw),
    );
  }

  @override
  Future<AppConfigSlice> getAppConfig() async {
    return testAppConfigSlice(
      content: <String, Object?>{
        'comment': <String, Object?>{
          'max_length': 500,
          'reply_preview_count': 1,
          'reply_expand_page_size': 10,
          'fold_line_count': 3,
          'attachment': <String, Object?>{'max_images': 1},
        },
        'feature_flags': <String, Object?>{
          'enable_create_action_entry': true,
          'enable_unified_create_editor': true,
          'enable_identity_based_surfaces': true,
          'enable_identity_share_template': true,
          'enable_article_distribution_profiles': true,
          'enable_article_book_reader': true,
          'enable_article_page_curl': true,
          'enable_assistant_content_identity_index': true,
        },
        'gray_release': <String, Object?>{
          'experiment_bucket': 'local_story_enabled',
          'current_stage': '100%',
          'canary_matrix': <Object?>[
            <String, Object?>{'stage': '5%', 'rolloutPercent': 5},
            <String, Object?>{'stage': '20%', 'rolloutPercent': 20},
            <String, Object?>{'stage': '50%', 'rolloutPercent': 50},
            <String, Object?>{'stage': '100%', 'rolloutPercent': 100},
          ],
        },
      },
    );
  }

  @override
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  }) async {
    if (postId.trim().isEmpty || idempotencyKey.trim().isEmpty) {
      throw ArgumentError(
        'DeletePost requires postId and caller-owned idempotencyKey',
      );
    }
    _deletedPostIds.add(postId);
    return PostDeletionReceipt(
      postId: postId.trim(),
      status: PostStatus.deleted,
      replayed: false,
    );
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
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
    return CursorPage<ContentPostViewData>(items: filtered, nextCursor: null);
  }

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

// ── 帖子/发现流域逻辑（原 content_repository_mock_posts.dart）───────────

extension _MockContentPosts on MockContentRepository {
  ContentPostViewData _mockPostDto(
    String postId, {
    required Map<String, dynamic> payloadMerge,
  }) {
    return contentPostViewDataFromReadModelMap(
      _mockPostWire(postId, payloadMerge: payloadMerge),
    );
  }

  Map<String, dynamic> _mockPostWire(
    String postId, {
    required Map<String, dynamic> payloadMerge,
  }) {
    Map<String, dynamic>? existingProjection;
    for (final post in _allDiscoveryPosts()) {
      if (post.id == postId) {
        existingProjection = _mockReadModelMapFromViewData(post);
        break;
      }
    }
    final merged = <String, dynamic>{
      'postId': postId,
      'authorId': 'mock_user',
      'displayName': 'Mock User',
      'avatarUrl': _mockContentDefaultAuthorAvatarUrl,
      'body': '',
      'imageUrls': <String>[],
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
      'publishedAt': DateTime.now().toUtc().toIso8601String(),
      'createdAt': DateTime.now().toUtc().toIso8601String(),
      'assistantUsePolicy': 'inherit',
      ...?existingProjection,
      ...payloadMerge,
    };
    merged['contentType'] = merged['contentType'] ?? merged.remove('type');
    merged['contentIdentity'] =
        merged['contentIdentity'] ?? merged.remove('identity');
    merged['authorDisplayName'] =
        merged['authorDisplayName'] ?? merged.remove('displayName');
    merged['authorAvatarUrl'] =
        merged['authorAvatarUrl'] ?? merged.remove('avatarUrl');
    merged['mediaUrls'] = merged['mediaUrls'] ?? merged.remove('imageUrls');
    merged.remove('_id');
    final type = merged['contentType']?.toString().trim() ?? '';
    if (type.isEmpty) {
      throw StateError('mock post type is required');
    }
    if (type == 'micro') {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'moment';
    } else {
      merged['contentIdentity'] = merged['contentIdentity'] ?? 'work';
    }
    return merged;
  }

  Map<String, dynamic>? _profilePreviewPostWireById(String postId) {
    final trimmed = postId.trim();
    if (trimmed.isEmpty || trimmed.endsWith('_gone')) {
      return null;
    }
    final separator = trimmed.lastIndexOf('_');
    if (separator <= 0 || separator == trimmed.length - 1) {
      return null;
    }
    final authorId = trimmed.substring(0, separator);
    final suffix = trimmed.substring(separator + 1).toLowerCase();
    if (authorId.isEmpty || suffix.length < 2) {
      return null;
    }
    final displayName = authorId == 'nature_photographer' ? '自然摄影师' : authorId;
    final base = <String, dynamic>{
      'authorId': authorId,
      'displayName': displayName,
      'avatarUrl': _mockContentDefaultAuthorAvatarUrl,
      'authorBackgroundUrl':
          'media/image/s/mock/seed/p_1506905925346-21bda4d32df4/v1/image.jpg',
      'createdAt': '2025-12-20T10:00:00Z',
    };
    if (suffix == 'video') {
      return _mockPostWire(
        trimmed,
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'video',
          'body': '森林的呼吸',
          'videoUrl':
              'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
          'thumbnailUrl':
              'media/image/s/mock/seed/p_1646034296147-d8ed3aace9a4/v1/image.jpg',
          'width': 720,
          'height': 1280,
          'durationMs': 30000,
          'likeCount': 840,
          'commentCount': 32,
          'shareCount': 25,
        },
      );
    }
    if (suffix.startsWith('a')) {
      return _mockPostWire(
        trimmed,
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'article',
          'title': '极简摄影的真谛',
          'body': '通过剥离不必要的元素，我们才能看见事物的本质。这是一篇关于极简主义摄影的思考与实践。',
          'coverUrl':
              'media/image/s/mock/seed/p_1627216661750-c59a4cea849c/v1/image.jpg',
          'likeCount': 2100,
          'commentCount': 78,
          'shareCount': 43,
        },
      );
    }
    if (suffix.startsWith('n')) {
      return _mockPostWire(
        trimmed,
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'micro',
          'body': '风吹过露台的时候',
          'imageUrls': <String>[],
          'likeCount': 420,
          'commentCount': 18,
          'shareCount': 6,
        },
      );
    }
    if (!suffix.startsWith('p')) {
      return null;
    }
    return _mockPostWire(
      trimmed,
      payloadMerge: <String, dynamic>{
        ...base,
        'type': 'image',
        'body': '光影的节奏',
        'coverUrl':
            'media/image/s/mock/seed/p_1647956450271-2ff54205bebf/v1/image.jpg',
        'imageUrls': <String>[
          'media/image/s/mock/seed/p_1647956450271-2ff54205bebf/v1/image.jpg',
        ],
        'width': 800,
        'height': 600,
        'likeCount': 1200,
        'commentCount': 45,
        'shareCount': 18,
      },
    );
  }

  List<ContentPostViewData> _profilePreviewPostsFor(String authorId) {
    if (authorId.isEmpty) {
      return const <ContentPostViewData>[];
    }
    final displayName = authorId == 'nature_photographer' ? '自然摄影师' : authorId;
    final base = <String, dynamic>{
      'authorId': authorId,
      'displayName': displayName,
      'avatarUrl': _mockContentDefaultAuthorAvatarUrl,
      'authorBackgroundUrl':
          'media/image/s/mock/seed/p_1506905925346-21bda4d32df4/v1/image.jpg',
    };
    return <ContentPostViewData>[
      _mockPostDto(
        '${authorId}_p1',
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'image',
          'body': '光影的节奏',
          'coverUrl':
              'media/image/s/mock/seed/p_1647956450271-2ff54205bebf/v1/image.jpg',
          'imageUrls': <String>[
            'media/image/s/mock/seed/p_1647956450271-2ff54205bebf/v1/image.jpg',
          ],
          'width': 800,
          'height': 600,
          'likeCount': 1200,
          'commentCount': 45,
          'shareCount': 18,
          'createdAt': '2025-12-20T10:00:00Z',
        },
      ),
      _mockPostDto(
        '${authorId}_video',
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'video',
          'body': '森林的呼吸',
          'videoUrl':
              'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
          'thumbnailUrl':
              'media/image/s/mock/seed/p_1646034296147-d8ed3aace9a4/v1/image.jpg',
          'width': 720,
          'height': 1280,
          'durationMs': 30000,
          'likeCount': 840,
          'commentCount': 32,
          'shareCount': 25,
          'createdAt': '2025-12-15T15:30:00Z',
        },
      ),
      _mockPostDto(
        '${authorId}_a1',
        payloadMerge: <String, dynamic>{
          ...base,
          'type': 'article',
          'title': '极简摄影的真谛',
          'body': '通过剥离不必要的元素，我们才能看见事物的本质。这是一篇关于极简主义摄影的思考与实践。',
          'coverUrl':
              'media/image/s/mock/seed/p_1627216661750-c59a4cea849c/v1/image.jpg',
          'likeCount': 2100,
          'commentCount': 78,
          'shareCount': 43,
          'createdAt': '2025-12-10T09:00:00Z',
        },
      ),
    ];
  }

  List<ContentPostViewData> _allDiscoveryPosts() {
    final seeded = _seedPosts;
    if (seeded != null) {
      return List<ContentPostViewData>.from(seeded, growable: false);
    }
    return _discoverySeedPosts();
  }

  Map<String, dynamic>? _contractSeedPostWire(String postId) {
    final trimmed = postId.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final raw = objectScenarioSeedReader.contentSeedSet()?['posts'];
    if (raw is! List) {
      return null;
    }
    for (final item in raw.whereType<Map>()) {
      final wire = item.cast<String, dynamic>();
      final itemId = wire['postId']?.toString() ?? '';
      if (itemId == trimmed) {
        return contentPostWireFromReadModelMap(wire);
      }
    }
    return null;
  }

  Future<List<ContentPostViewData>> _resolveDiscoveryPosts({
    required String category,
    String? identity,
    String? type,
  }) async {
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

  Future<List<ContentPostViewData>> _alphaShowcasePosts() async {
    return ContentMockData.seededShowcaseFeedItemsAsync();
  }

  Future<Map<String, dynamic>?> _alphaShowcasePostWireById(
    String postId,
  ) async {
    final trimmed = postId.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final showcase = await ContentMockData.seededShowcaseFeedItemsAsync();
    for (final item in showcase) {
      if (item.id == trimmed) {
        final row = _mockReadModelMapFromViewData(item);
        if ((row['type']?.toString() ?? '') == 'article') {
          return ContentMockData.articleWireByPostId(trimmed) ?? row;
        }
        return row;
      }
    }
    return null;
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
    ContentPostViewData post, {
    String? identity,
    String? type,
  }) {
    final expectedIdentity = (identity ?? '').trim();
    final expectedType = _normalizeFeedType(type);
    if (expectedIdentity.isNotEmpty && post.identity != expectedIdentity) {
      return false;
    }
    return expectedType == null || post.type == expectedType;
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
}

// ── 足迹替身（原 lib footprint_repository.dart 的 Mock 实现）────────────

/// contract fixture（footprint_core）单一真相源；postRef join
/// content_discovery_core.posts，不复制第二套内容数据。
class MockFootprintRepository implements FootprintRepository {
  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  }) async {
    final seed = objectScenarioSeedReader.contentSeedSet('footprint_core');
    final rawItems = seed?['items'];
    if (rawItems is! List) {
      return const CursorPage<FootprintEntry>(items: <FootprintEntry>[]);
    }
    final postsById = _discoveryPostsById();
    final normalizedType = (type ?? '').trim().toLowerCase();
    final entries = <FootprintEntry>[];
    for (final raw in rawItems.whereType<Map>()) {
      final item = raw.cast<String, dynamic>();
      final itemType = (item['type'] ?? '').toString().toLowerCase();
      if (normalizedType.isNotEmpty && itemType != normalizedType) {
        continue;
      }
      final postRef = (item['postRef'] ?? '').toString();
      final postMap = postsById[postRef];
      entries.add(
        FootprintEntry(
          postId: postRef,
          action: (item['action'] ?? '').toString(),
          occurredAt: _isoMinusHours(item['occurredAgoHours']),
          post: postMap != null
              ? contentPostViewDataFromReadModelMap(postMap)
              : null,
        ),
      );
    }
    final start = int.tryParse(cursor ?? '') ?? 0;
    final window = entries.skip(start).take(limit).toList(growable: false);
    final nextOffset = start + window.length;
    return CursorPage<FootprintEntry>(
      items: window,
      nextCursor: nextOffset < entries.length ? '$nextOffset' : null,
    );
  }

  static Map<String, Map<String, dynamic>> _discoveryPostsById() {
    final seed = objectScenarioSeedReader.contentSeedSet();
    final rawPosts = seed?['posts'];
    final byId = <String, Map<String, dynamic>>{};
    if (rawPosts is List) {
      for (final raw in rawPosts.whereType<Map>()) {
        final map = raw.cast<String, dynamic>();
        final id = (map['postId'] ?? '').toString();
        if (id.isNotEmpty) {
          byId[id] = map;
        }
      }
    }
    return byId;
  }

  static String _isoMinusHours(Object? agoHours) {
    final hours = agoHours is num ? agoHours.toInt() : 0;
    return DateTime.now()
        .toUtc()
        .subtract(Duration(hours: hours))
        .toIso8601String();
  }
}
