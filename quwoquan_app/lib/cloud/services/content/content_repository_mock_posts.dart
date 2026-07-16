part of 'content_repository.dart';

// MockContentRepository 的帖子 / 发现流域逻辑（帖子 wire 合成、契约/资料页种子、
// 发现流归类与 identity/type 匹配）。与 content_repository_mock.dart 同库（part），
// 共享私有实例状态；拆出仅为收敛主文件行数（R03），不构成第二数据源（R15/R24）。

const String _mockContentDefaultAuthorAvatarUrl =
    'media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png';

List<PostBaseDto>? _contractSeedPosts() {
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

List<PostBaseDto> _discoverySeedPosts() {
  return aggregateDiscoveryWireSlices(
    showcase: ContentMockData.seededShowcaseFeedItems,
    photo: ContentMockData.discoveryPhotoData,
    video: ContentMockData.discoveryVideoData,
    moment: ContentMockData.discoveryMomentData,
    article: ContentMockData.discoveryArticleData,
  ).map(postBaseDtoFromMap).toList(growable: false);
}

List<PostBaseDto> _mergePostSeeds(
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

extension _MockContentPosts on MockContentRepository {
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
      'authorAvatarUrl': _mockContentDefaultAuthorAvatarUrl,
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
      'authorAvatarUrl': _mockContentDefaultAuthorAvatarUrl,
      'authorBackgroundUrl':
          'media/image/s/mock/seed/p_1506905925346-21bda4d32df4/v1/image.jpg',
      'createdAt': '2025-12-20T10:00:00Z',
    };
    if (suffix.startsWith('v')) {
      return _mockPostWire(
        trimmed,
        payloadMerge: <String, dynamic>{
          ...base,
          'contentType': 'video',
          'body': '森林的呼吸',
          'videoUrl':
              'media/video/s/mock/external/flutter/butterfly/v1/video.mp4',
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
          'contentType': 'article',
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
          'contentType': 'micro',
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
        'contentType': 'image',
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

  List<PostBaseDto> _profilePreviewPostsFor(String authorId) {
    if (authorId.isEmpty) {
      return const <PostBaseDto>[];
    }
    final displayName = authorId == 'nature_photographer' ? '自然摄影师' : authorId;
    final base = <String, dynamic>{
      'authorId': authorId,
      'displayName': displayName,
      'authorAvatarUrl': _mockContentDefaultAuthorAvatarUrl,
      'authorBackgroundUrl':
          'media/image/s/mock/seed/p_1506905925346-21bda4d32df4/v1/image.jpg',
    };
    return <PostBaseDto>[
      _mockPostDto(
        '${authorId}_p1',
        payloadMerge: <String, dynamic>{
          ...base,
          'contentType': 'image',
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
        '${authorId}_v1',
        payloadMerge: <String, dynamic>{
          ...base,
          'contentType': 'video',
          'body': '森林的呼吸',
          'videoUrl':
              'media/video/s/mock/external/flutter/butterfly/v1/video.mp4',
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
          'contentType': 'article',
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

  Future<List<PostBaseDto>> _resolveDiscoveryPosts({
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

  Future<List<PostBaseDto>> _alphaShowcasePosts() async {
    final showcase = await ContentMockData.seededShowcaseFeedItemsAsync();
    return showcase
        .map((item) => postBaseDtoFromMap(item.toDiscoveryWireMap()))
        .toList(growable: false);
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
        final row = item.toDiscoveryWireMap();
        if ((row['contentType']?.toString() ?? row['type']?.toString() ?? '') ==
            'article') {
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
}
