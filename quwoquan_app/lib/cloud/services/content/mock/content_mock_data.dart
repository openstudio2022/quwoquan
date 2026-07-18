// ignore_for_file: prefer_single_quotes
import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/content/mock/generated/home_showcase_core_fixture.g.dart';

/// 内容域 mock 数据（canonical 字段，与 FeedItemDto schema 严格对齐）。
///
/// 字段命名以 _projections/discovery_feed.yaml client_projection 为权威：
/// - authorId / displayName / avatarUrl（扁平，无嵌套 user/author sub-map）
/// - coverUrl / thumbnailUrl / imageUrls / videoUrl（media 规范化）
/// - likeCount / commentCount / shareCount（count 后缀）
/// - body / title（正文 / 标题）
/// - createdAt（ISO 8601）
class ContentMockData {
  ContentMockData._();

  static List<FeedItemDto> _withCanonicalMedia(
    List<Map<String, dynamic>> items,
  ) {
    return items
        .map((raw) => FeedItemDto.fromMap(Map<String, dynamic>.from(raw)))
        .toList(growable: false);
  }

  static List<FeedItemDto> _expandDiscoveryFeed(
    List<FeedItemDto> source, {
    required int targetCount,
    required String cloneLabel,
  }) {
    if (source.length >= targetCount) {
      return source;
    }
    final expanded = <FeedItemDto>[...source];
    var cloneIndex = 1;
    while (expanded.length < targetCount) {
      final base = source[(expanded.length - source.length) % source.length];
      expanded.add(
        base.copyWith(
          id: '${base.id}_${cloneLabel}_$cloneIndex',
          title: base.title == null || base.title!.trim().isEmpty
              ? base.title
              : '${base.title} · ${cloneIndex + 1}',
          summary: base.summary == null || base.summary!.trim().isEmpty
              ? base.summary
              : '${base.summary}（扩展批次 ${cloneIndex + 1}）',
          createdAt: base.createdAt.subtract(Duration(minutes: cloneIndex)),
        ),
      );
      cloneIndex += 1;
    }
    return List<FeedItemDto>.unmodifiable(expanded);
  }

  /// alpha showcase 全样式样本：唯一真相源为 contract seed `home_showcase_core`
  /// （content_scenarios[.lite|.gamma-curated].json），四环境同源 archived 媒体。
  /// MockRepository 与发现区 wire 查找均消费本 getter，端侧不再维护第二套样本列表。
  static List<FeedItemDto> get seededShowcaseFeedItems {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(
      'home_showcase_core',
    );
    final hostSeed = _feedItemsFromSeed(seed);
    if (hostSeed.isNotEmpty) {
      return hostSeed;
    }
    return _feedItemsFromPostsJson(kHomeShowcaseCorePostsJson);
  }

  /// 移动端运行时无法读取宿主仓库文件，必须使用随 App 编译进来的生成常量。
  /// host-side 测试仍优先使用 [seededShowcaseFeedItems] 的 contract fixture 读链。
  static Future<List<FeedItemDto>> seededShowcaseFeedItemsAsync() async {
    return seededShowcaseFeedItems;
  }

  static List<FeedItemDto> _feedItemsFromPostsJson(String raw) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <FeedItemDto>[];
      }
      return decoded
          .whereType<Map>()
          .map((item) => FeedItemDto.fromMap(item.cast<String, dynamic>()))
          .toList(growable: false);
    } catch (_) {
      return const <FeedItemDto>[];
    }
  }

  static List<FeedItemDto> _feedItemsFromSeed(Object? seed) {
    if (seed is! Map) {
      return const <FeedItemDto>[];
    }
    final posts = seed['posts'];
    if (posts is! List) {
      return const <FeedItemDto>[];
    }
    return posts
        .whereType<Map>()
        .map((item) => FeedItemDto.fromMap(item.cast<String, dynamic>()))
        .toList(growable: false);
  }

  static String _buildLongformMockArticleMarkdown({
    required String title,
    required String summary,
    required String template,
    required String fontPreset,
    required String coverUrl,
    List<String> imageUrls = const <String>[],
  }) {
    final normalizedTitle = title.trim().isEmpty ? '无题长文' : title.trim();
    final normalizedSummary = summary.trim().isEmpty
        ? '这是一段用于精品沉浸翻页的长文样本。'
        : summary.trim();
    final resolvedImages = imageUrls.where((url) => url.trim().isNotEmpty);
    final figureUrls = resolvedImages.isEmpty && coverUrl.trim().isNotEmpty
        ? <String>[coverUrl.trim()]
        : resolvedImages.toList(growable: false);
    final repeatedParagraph = [
      normalizedSummary,
      '为了保证首页精品与文章浏览入口都能稳定验证翻页，这里把摘要扩展为更长的连续正文。',
      '正文继续补充场景、细节、人物动作与环境变化，让排版在窄屏沉浸视口中稳定切出第二页、第三页。',
      '当用户在首页精品中停留到文章卡时，应该能像真实长文一样完成前翻、后翻，而不是停留在单页摘要。',
    ].join('\n\n');
    final figures = figureUrls.isEmpty
        ? ''
        : figureUrls.indexed
              .map((entry) {
                final index = entry.$1 + 1;
                final url = entry.$2;
                final caption = figureUrls.length > 1
                    ? '精品长文配图 $index'
                    : '精品长文封面';
                return ':::figure id="image_${normalizedTitle.hashCode}_$index" layout="fullWidth" caption="$caption"\n$url\n:::\n';
              })
              .join('\n');
    return '---\n'
        'title: $normalizedTitle\n'
        'summary: $normalizedSummary\n'
        'template: $template\n'
        'fontPreset: $fontPreset\n'
        '---\n\n'
        '# $normalizedTitle\n\n'
        '$normalizedSummary\n'
        '$figures\n'
        '## 开篇\n\n'
        '$repeatedParagraph\n\n'
        '## 展开\n\n'
        '$repeatedParagraph\n\n'
        '## 收束\n\n'
        '$repeatedParagraph\n';
  }

  static Map<String, dynamic> _buildArticleMarkdownSource({
    required String title,
    required String intro,
    required String heading,
    required String sectionBody,
    required String conclusion,
    String imageUrl = '',
    String imageLayout = 'fullWidth',
    String caption = '',
  }) {
    final blocks = <Map<String, dynamic>>[
      {'id': '${title.hashCode}_p0', 'type': 'paragraph', 'text': intro},
      {'id': '${title.hashCode}_h2', 'type': 'heading2', 'text': heading},
      if (imageUrl.isNotEmpty)
        {
          'id': '${title.hashCode}_img',
          'type': 'image',
          'imageUrl': imageUrl,
          'imageLayout': imageLayout,
          'caption': caption,
        },
      {'id': '${title.hashCode}_p1', 'type': 'paragraph', 'text': sectionBody},
      {'id': '${title.hashCode}_section', 'type': 'sectionTitle', 'text': '收束'},
      {'id': '${title.hashCode}_p2', 'type': 'paragraph', 'text': conclusion},
    ];
    return <String, dynamic>{
      'title': title,
      'body': <String>[
        intro,
        heading,
        sectionBody,
        conclusion,
      ].where((segment) => segment.trim().isNotEmpty).join('\n'),
      'assets': imageUrl.isEmpty
          ? const <Map<String, dynamic>>[]
          : <Map<String, dynamic>>[
              {
                'id': '${title.hashCode}_asset',
                'offset': intro.length + heading.length,
                'imageUrl': imageUrl,
                'imageLayout': imageLayout,
                'caption': caption,
              },
            ],
      'blocks': blocks,
    };
  }

  /// 单篇文章详情 mock（与 [discoveryArticleData] / [getPost] 同源，按 postId 查找）。
  static Map<String, dynamic>? articleWireByPostId(String id) {
    final trimmed = id.trim();
    if (trimmed.isEmpty) return null;
    try {
      final row = <FeedItemDto>[
        ...discoveryArticleData,
        ...seededShowcaseFeedItems.where((item) => item.type == 'article'),
      ].firstWhere((a) => a.id == trimmed);
      final title = row.title ?? '';
      final summary = row.summary ?? row.body ?? '';
      final imageUrls = row.imageUrls
          .map((url) => url.trim())
          .where((url) => url.isNotEmpty)
          .toList(growable: false);
      final markdown = _buildLongformMockArticleMarkdown(
        title: title,
        summary: summary,
        template: row.articleTemplate ?? 'journal',
        fontPreset: row.articleFontPreset ?? 'clean',
        coverUrl: row.coverUrl,
        imageUrls: imageUrls,
      );
      return <String, dynamic>{
        ...row.toDiscoveryWireMap(),
        'id': row.id,
        'type': 'article',
        'articleMarkdown': markdown,
        'markdownDialect': 'qwq-rich-md',
        'articleAssetManifest': const <String, dynamic>{'assets': []},
        'articleRenderProfile': <String, dynamic>{
          'template': row.articleTemplate ?? 'journal',
          'fontPreset': row.articleFontPreset ?? 'clean',
        },
      };
    } catch (_) {
      return null;
    }
  }

  static Map<String, dynamic> _buildArticlePost({
    required String postId,
    required String authorId,
    required String displayName,
    required String authorAvatarUrl,
    required String authorBackgroundUrl,
    required String title,
    required String summary,
    required String articleTemplate,
    required String articleFontPreset,
    required Map<String, dynamic> articleMarkdownSource,
    required int likeCount,
    required int commentCount,
    required int shareCount,
    required String createdAt,
    String coverUrl = '',
    List<String> mediaUrls = const <String>[],
    List<Map<String, dynamic>> intersectionReasons =
        const <Map<String, dynamic>>[],
  }) {
    final normalizedCoverUrl = coverUrl.trim();
    final normalizedMediaUrls = mediaUrls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
    final articleMediaUrls =
        normalizedMediaUrls.isEmpty && normalizedCoverUrl.isNotEmpty
        ? <String>[normalizedCoverUrl]
        : normalizedMediaUrls;
    return <String, dynamic>{
      'id': postId,
      'type': 'article',
      'identity': 'work',
      'authorId': authorId,
      'displayName': displayName,
      'avatarUrl': authorAvatarUrl,
      'authorBackgroundUrl': authorBackgroundUrl,
      'title': title,
      'body': summary,
      'summary': summary,
      if (normalizedCoverUrl.isNotEmpty) 'coverUrl': normalizedCoverUrl,
      if (normalizedCoverUrl.isNotEmpty) 'thumbnailUrl': normalizedCoverUrl,
      if (articleMediaUrls.isNotEmpty) 'imageUrls': articleMediaUrls,
      'articleTemplate': articleTemplate,
      'articleFontPreset': articleFontPreset,
      'articlePresentationVersion': 1,
      'articleMarkdownDigest': 'mock-md:$postId',
      'articleRenderProfile': <String, dynamic>{
        'template': articleTemplate,
        'fontPreset': articleFontPreset,
        'layoutPolicy': const <String, Object?>{
          'wrapDowngrade': 'compactWidthToFullWidth',
          'galleryDowngrade': 'singleColumn',
        },
      },
      'likeCount': likeCount,
      'commentCount': commentCount,
      'shareCount': shareCount,
      'createdAt': createdAt,
      if (intersectionReasons.isNotEmpty)
        'intersectionReasons': intersectionReasons,
    };
  }

  // ─── Photo feed（美图 tab）─────────────────────────────────────────────────

  // width/height：主图尺寸（px），用于前端直接计算宽高比，无需请求图片元数据。
  // 比例来源于 Unsplash 图片的真实宽高比。
  // authorBackgroundUrl：作者主页背景图，每个作者 ID 固定一张。
  static List<FeedItemDto> get discoveryPhotoData => _expandDiscoveryFeed(
    _withCanonicalMedia([
      {
        'id': 'd1',
        'type': 'image',
        'authorId': 'nature_photographer',
        'displayName': '自然摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 960,
        'height': 800,
        'likeCount': 1200,
        'commentCount': 45,
        'shareCount': 18,
        'createdAt': '2025-12-20T10:00:00Z',
      },
      {
        'id': 'd2',
        'type': 'image',
        'authorId': 'travel_photographer',
        'displayName': '旅行摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 640,
        'height': 800,
        'likeCount': 890,
        'commentCount': 32,
        'shareCount': 25,
        'createdAt': '2025-12-19T15:30:00Z',
      },
      {
        'id': 'd4',
        'type': 'image',
        'authorId': 'street_photo',
        'displayName': '街头摄影',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 800,
        'height': 800,
        'likeCount': 2300,
        'commentCount': 78,
        'shareCount': 67,
        'createdAt': '2025-12-18T08:00:00Z',
      },
      {
        'id': 'd5',
        'type': 'image',
        'authorId': 'nature_photographer',
        'displayName': '自然摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 1200,
        'height': 800,
        'likeCount': 1800,
        'commentCount': 56,
        'shareCount': 42,
        'createdAt': '2025-12-17T12:00:00Z',
      },
      {
        'id': 'd6',
        'type': 'image',
        'authorId': 'travel_photographer',
        'displayName': '旅行摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 800,
        'height': 1067,
        'likeCount': 650,
        'commentCount': 21,
        'shareCount': 14,
        'createdAt': '2025-12-16T09:20:00Z',
      },
      {
        'id': 'd10',
        'type': 'image',
        'authorId': 'street_photo',
        'displayName': '街头摄影',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 1200,
        'height': 800,
        'likeCount': 430,
        'commentCount': 15,
        'shareCount': 8,
        'createdAt': '2025-12-15T14:00:00Z',
      },
      {
        'id': 'd11',
        'type': 'image',
        'authorId': 'nature_photographer',
        'displayName': '自然摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 800,
        'height': 534,
        'likeCount': 920,
        'commentCount': 38,
        'shareCount': 27,
        'createdAt': '2025-12-14T11:30:00Z',
      },
      {
        'id': 'd12',
        'type': 'image',
        'authorId': 'travel_photographer',
        'displayName': '旅行摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 800,
        'height': 600,
        'likeCount': 1100,
        'commentCount': 44,
        'shareCount': 33,
        'createdAt': '2025-12-13T16:00:00Z',
      },
      {
        'id': 'd13',
        'type': 'image',
        'authorId': 'street_photo',
        'displayName': '街头摄影',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 800,
        'height': 534,
        'likeCount': 780,
        'commentCount': 29,
        'shareCount': 19,
        'createdAt': '2025-12-12T08:45:00Z',
      },
      {
        'id': 'd14',
        'type': 'image',
        'authorId': 'nature_photographer',
        'displayName': '自然摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'imageUrls': [
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        ],
        'width': 1200,
        'height': 800,
        'likeCount': 1560,
        'commentCount': 62,
        'shareCount': 48,
        'createdAt': '2025-12-11T10:00:00Z',
      },
    ]),
    targetCount: 24,
    cloneLabel: 'photo',
  );

  // ─── Video feed（视频 tab）─────────────────────────────────────────────────
  // width/height：视频分辨率（px），处理管道写入。
  // 竖屏短视频通常为 1080×1920，横屏为 1920×1080。

  static List<FeedItemDto> get discoveryVideoData => _expandDiscoveryFeed(
    _withCanonicalMedia([
      {
        'id': 'v1',
        'type': 'video',
        'authorId': 'a1',
        'displayName': '楹语小筑',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'videoUrl':
            'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
        'body': '东京凌晨两点的街道，有一种难以言喻的孤独美。#治愈系 #东京之夜 #氛围感',
        'width': 1080,
        'height': 1920,
        'likeCount': 12500,
        'commentCount': 892,
        'shareCount': 1200,
        'durationMs': 45000,
        'musicName': 'Tokyo Midnight Lofi',
        'createdAt': '2026-01-10T02:00:00Z',
      },
      {
        'id': 'v2',
        'type': 'video',
        'authorId': 'a2',
        'displayName': '自然摄影师',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'videoUrl':
            'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
        'body': '在大自然中找回内心的平静。🌲✨ #森林漫步 #自然景观 #心灵治愈',
        'width': 1080,
        'height': 1920,
        'likeCount': 8200,
        'commentCount': 430,
        'shareCount': 560,
        'durationMs': 15000,
        'musicName': 'Forest Whispers',
        'createdAt': '2026-01-09T10:30:00Z',
      },
      {
        'id': 'v3',
        'type': 'video',
        'authorId': 'a3',
        'displayName': '未来科技',
        'avatarUrl':
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        'authorBackgroundUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'coverUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'thumbnailUrl':
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'videoUrl':
            'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
        'body': '2026年，我们的生活将如何被AI改变？一分钟带你了解。#科技趋势 #未来已来',
        'width': 1920,
        'height': 1080,
        'likeCount': 45000,
        'commentCount': 3400,
        'shareCount': 12000,
        'durationMs': 59000,
        'musicName': 'Digital Future Beats',
        'createdAt': '2026-01-08T20:00:00Z',
      },
    ]),
    targetCount: 24,
    cloneLabel: 'video',
  );

  // ─── Moment feed（微趣 tab）───────────────────────────────────────────────

  static List<FeedItemDto> get discoveryMomentData => _withCanonicalMedia([
    {
      'id': 'm4',
      'type': 'micro',
      'authorId': 'u4',
      'displayName': '李想',
      'avatarUrl':
          'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
      'authorBackgroundUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'body':
          '看他飞奔下车的样子，真帅！如果谁能联系上车主，能不能帮我转告一下，我可不可以去请他吃个饭？ //@理想汽车:点赞每一份挺身而出的勇气！',
      'likeCount': 1581,
      'commentCount': 301,
      'shareCount': 112,
      'createdAt': '2026-01-15T10:00:00Z',
    },
    {
      'id': 'm1',
      'type': 'micro',
      'authorId': 'u1',
      'displayName': '你的皮炎有点辣',
      'avatarUrl':
          'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
      'authorBackgroundUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'body': '左边是董宇辉的办公室，右边是俞敏洪的办公室，说明什么？',
      'imageUrls': [
        'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      ],
      'likeCount': 234,
      'commentCount': 36,
      'shareCount': 4,
      'createdAt': '2026-01-14T10:56:00Z',
      'intersectionReasons': [
        {
          'dimension': 'identity',
          'tagRefs': ['identity/campus/xdf'],
          'label': '同校',
          'sharedCount': 3,
          'strength': 0.82,
          'displayText': '你和 TA 都来自新东方校友圈',
          'objectKind': 'person',
          'relationObjectId': 'u1',
          'actionType': 'follow',
          'actionTargetId': 'u1',
          'source': 'identity',
        },
        {
          'dimension': 'identity',
          'tagRefs': ['identity/org/xdf-alumni'],
          'label': '同组织',
          'sharedCount': 2,
          'strength': 0.7,
          'displayText': '你和 TA 都属于新东方校友会',
          'objectKind': 'school',
          'relationObjectId': 'fixture_homepage_school_neworiental',
          'actionType': 'view',
          'actionTargetId': 'fixture_homepage_school_neworiental',
          'source': 'identity',
        },
      ],
    },
    {
      'id': 'm2',
      'type': 'micro',
      'authorId': 'u2',
      'displayName': '仅分组可见',
      'avatarUrl':
          'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
      'authorBackgroundUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'body': '最害怕的事情还是发生了，船过去了船夫没赶上……',
      'coverUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'videoUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'durationMs': 15000,
      'likeCount': 452,
      'commentCount': 18,
      'shareCount': 37,
      'createdAt': '2026-01-13T00:00:00Z',
      'intersectionReasons': [
        {
          'dimension': 'location',
          'tagRefs': ['location/geo/west-lake'],
          'label': '同游',
          'sharedCount': 5,
          'strength': 0.76,
          'displayText': '你和 TA 都去过 西湖',
          'objectKind': 'place',
          'relationObjectId': 'homepage_sight_west_lake',
          'actionType': 'view',
          'actionTargetId': 'homepage_sight_west_lake',
          'source': 'location',
        },
      ],
    },
    {
      'id': 'm3',
      'type': 'micro',
      'authorId': 'u3',
      'displayName': '原价帝吧',
      'avatarUrl':
          'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
      'authorBackgroundUrl':
          'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      'body':
          '只要我不尴尬，尴尬的就是别人——投资金银的侃爷Kanye West和妻子比安卡 Bianca Censori 出镜混剪📷 #金银V型反转##黄金#',
      'imageUrls': List<String>.generate(
        9,
        (i) =>
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      ),
      'likeCount': 1560,
      'commentCount': 420,
      'shareCount': 89,
      'createdAt': '2026-01-12T08:00:00Z',
      'intersectionReasons': [
        {
          'dimension': 'interest',
          'tagRefs': ['interest/topic/gold-invest'],
          'label': '兴趣相近',
          'sharedCount': 8,
          'strength': 0.91,
          'displayText': '你们都在关注 黄金投资',
          'objectKind': 'circle',
          'relationObjectId': 'fixture_circle_gold_invest',
          'actionType': 'join',
          'actionTargetId': 'fixture_circle_gold_invest',
          'source': 'content',
        },
      ],
    },
  ]);

  // ─── Article feed（文章 tab）──────────────────────────────────────────────

  static List<FeedItemDto> get discoveryArticleData => _expandDiscoveryFeed(
    _withCanonicalMedia([
      _buildArticlePost(
        postId: 'web-dev',
        authorId: 'tech_daily',
        displayName: 'TechDaily',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '2024年现代Web开发趋势：从服务端组件到边缘计算',
        summary: '服务端组件把获取数据前移，Edge Runtime 让首屏和交互都更轻更快。',
        articleTemplate: 'tech',
        articleFontPreset: 'mono',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '2024年现代Web开发趋势：从服务端组件到边缘计算',
          intro: '服务端组件正在把前端从“先拿数据再渲染”改写成“边生成边送达”。',
          heading: '范式切换',
          sectionBody: '当数据和组件在同一侧拼装，团队就能把耗时工作前移到响应流之前。',
          conclusion: '真正的竞争力不是概念堆叠，而是把复杂性稳定地收敛在交付链路里。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '边缘节点覆盖图',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 1240,
        commentCount: 56,
        shareCount: 89,
        createdAt: '2026-01-15T08:00:00Z',
      ),
      _buildArticlePost(
        postId: 'calligraphy',
        authorId: 'mo_yun',
        displayName: '墨韵',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '墨韵流芳：汉字书法中的空间美学与精神寄托',
        summary: '在黑与白的克制之间，真正被书写出来的是节奏、呼吸与精神张力。',
        articleTemplate: 'ritual',
        articleFontPreset: 'classic',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '墨韵流芳：汉字书法中的空间美学与精神寄托',
          intro: '书法之美，从来不只是线条本身，而是线条与留白共同构成的秩序。',
          heading: '起笔与呼吸',
          sectionBody: '提按顿挫里的停留感，决定了一幅作品是否拥有“气口”和韵律。',
          conclusion: '当代排版若能保留这种呼吸，传统精神便会自然落进今天的阅读里。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapLeft',
          caption: '纸墨细节',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 892,
        commentCount: 34,
        shareCount: 12,
        createdAt: '2026-01-14T00:00:00Z',
      ),
      _buildArticlePost(
        postId: 'pasta',
        authorId: 'chef_mario',
        displayName: 'Chef Mario',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '意式风情：三种经典酱汁的制作秘籍',
        summary: '从红酱到白酱，决定一盘面条记忆点的，是火候与节奏的控制。',
        articleTemplate: 'gentle',
        articleFontPreset: 'rounded',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '意式风情：三种经典酱汁的制作秘籍',
          intro: '一盘看似简单的意面，真正的层次往往藏在酱汁的时间管理里。',
          heading: '火候与浓度',
          sectionBody: '慢炖让番茄的尖锐酸感被柔化，奶香与香草会在最后阶段完成收口。',
          conclusion: '家庭厨房最值得守住的是“不过度”，让每一种味道都留有余地。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'fullWidth',
          caption: '装盘示意',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 2105,
        commentCount: 142,
        shareCount: 304,
        createdAt: '2026-01-12T00:00:00Z',
      ),
      _buildArticlePost(
        postId: 'art_1',
        authorId: 'design_guru',
        displayName: 'DesignGuru',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: 'UI设计的心理学原理：色彩、布局与用户认知',
        summary: '视觉系统不是装饰，色彩和留白本质上都在影响用户的决策速度。',
        articleTemplate: 'diffuse',
        articleFontPreset: 'clean',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: 'UI设计的心理学原理：色彩、布局与用户认知',
          intro: '用户对界面的第一判断，往往在阅读前就已经开始。',
          heading: '色彩心理',
          sectionBody: '高饱和冷色常被感知为理性和科技，暖色则更容易制造行动冲动。',
          conclusion: '一套有效的视觉语言，关键不在堆叠细节，而在让路径更容易被理解。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapLeft',
          caption: '设计评审样例',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 3200,
        commentCount: 120,
        shareCount: 450,
        createdAt: '2026-01-15T05:00:00Z',
      ),
      _buildArticlePost(
        postId: 'journal_cover',
        authorId: 'travel_note',
        displayName: '山川手账',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '一座山的晨雾：把徒步记成一本可以翻页的手账',
        summary: '旅行不是景点清单，而是一连串被光线、气味和脚步慢慢浸透的感受。',
        articleTemplate: 'journal',
        articleFontPreset: 'handwritten',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '一座山的晨雾：把徒步记成一本可以翻页的手账',
          intro: '凌晨出发时，山路还裹着湿气，鞋底踩下去像踩进一页没晒干的纸。',
          heading: '边走边贴',
          sectionBody: '把票据、路线、海拔和一句突然冒出的心情都贴进同一页，旅程就有了体温。',
          conclusion: '好的手账从不追求完整，它只保留那些会在很久之后再次把人带回去的瞬间。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '晨雾扉页',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 1460,
        commentCount: 61,
        shareCount: 88,
        createdAt: '2026-01-11T07:20:00Z',
      ),
      _buildArticlePost(
        postId: 'tech_plain',
        authorId: 'infra_log',
        displayName: 'InfraLog',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '从日志到观测：团队如何为真实故障建立共同语言',
        summary: '真正有效的观测不是面板越多越好，而是每个角色都能找到自己的判断入口。',
        articleTemplate: 'tech',
        articleFontPreset: 'clean',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '从日志到观测：团队如何为真实故障建立共同语言',
          intro: '故障发生时最昂贵的不是恢复时间，而是团队对“问题正在发生什么”没有共同理解。',
          heading: '事件对齐',
          sectionBody: '把日志、指标和 tracing 串在同一语义下，排障链路才不会被多套命名撕裂。',
          conclusion: '观测最终服务的是决策速度，而不是仪表盘本身的复杂程度。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '监控面板草图',
        ),
        likeCount: 980,
        commentCount: 42,
        shareCount: 61,
        createdAt: '2026-01-10T09:00:00Z',
      ),
      _buildArticlePost(
        postId: 'ritual_plain',
        authorId: 'ink_house',
        displayName: '纸上居',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '雨夜读帖：为什么东方手卷总能让人慢下来',
        summary: '慢不是效率的反义词，而是一种把注意力重新还给阅读对象的方式。',
        articleTemplate: 'ritual',
        articleFontPreset: 'classic',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '雨夜读帖：为什么东方手卷总能让人慢下来',
          intro: '展开手卷时，视线被主动限制在一小段距离里，速度因此自然被放缓。',
          heading: '节奏控制',
          sectionBody: '纸张纹理、行距和墨色密度一起把阅读的呼吸感重新带了回来。',
          conclusion: '当媒介本身参与叙事，阅读就不只是理解信息，而是进入一种状态。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapLeft',
          caption: '卷页细节',
        ),
        likeCount: 730,
        commentCount: 26,
        shareCount: 18,
        createdAt: '2026-01-09T19:30:00Z',
      ),
      _buildArticlePost(
        postId: 'gentle_plain',
        authorId: 'home_writer',
        displayName: '慢慢生活',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '把周末过成一页柔软的家居笔记',
        summary: '家并不需要每天焕新，真正改变气氛的是一些安静但持续的微调。',
        articleTemplate: 'gentle',
        articleFontPreset: 'clean',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '把周末过成一页柔软的家居笔记',
          intro: '窗帘被换成更透光的材质后，客厅在下午会像一张慢慢被晒暖的纸。',
          heading: '轻调整',
          sectionBody: '靠枕、香气、桌面杂物和灯光色温的微调，比一次性大改造更能改变居住体感。',
          conclusion: '生活质感不总来自昂贵物件，更多时候来自对日常节奏的认真照顾。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapLeft',
          caption: '窗边一角',
        ),
        likeCount: 1186,
        commentCount: 74,
        shareCount: 103,
        createdAt: '2026-01-08T12:15:00Z',
      ),
      _buildArticlePost(
        postId: 'diffuse_plain',
        authorId: 'visual_lab',
        displayName: '视觉实验室',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '把留白做成节奏：信息界面里的“呼吸设计”',
        summary: '所谓高级感并不是更空，而是让信息的停顿和推进都变得可预测。',
        articleTemplate: 'diffuse',
        articleFontPreset: 'clean',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '把留白做成节奏：信息界面里的“呼吸设计”',
          intro: '当内容变多，留白真正承担的职责是让用户愿意继续往下看。',
          heading: '节奏设计',
          sectionBody: '留白不只是空着，它和字号、段落密度、卡片间距一起决定了浏览阻力。',
          conclusion: '界面一旦会呼吸，用户就更容易把注意力留在信息本身，而不是控件噪音上。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '版式网格',
        ),
        likeCount: 1540,
        commentCount: 67,
        shareCount: 95,
        createdAt: '2026-01-07T18:40:00Z',
      ),
      _buildArticlePost(
        postId: 'journal_plain',
        authorId: 'field_notes',
        displayName: '田野笔记',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '城市散步的边角料，如何变成一本值得反复翻的小册子',
        summary: '真正让人想保存下来的，不是完整纪实，而是那些被贴在边角里的细小瞬间。',
        articleTemplate: 'journal',
        articleFontPreset: 'rounded',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '城市散步的边角料，如何变成一本值得反复翻的小册子',
          intro: '一张收据、一段路名和一处树影，就足够撑起一页有情绪的散步记录。',
          heading: '贴纸与证据',
          sectionBody: '当票据、时间、天气和一句突然冒出的感受被并排放下，城市会重新长出层次。',
          conclusion: '好的手账不负责证明你去了哪里，它负责提醒你当时为什么会想停下来。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '散步拾片',
        ),
        likeCount: 865,
        commentCount: 39,
        shareCount: 44,
        createdAt: '2026-01-06T16:05:00Z',
      ),
      _buildArticlePost(
        postId: 'diffuse_cover_body_only',
        authorId: 'signal_notes',
        displayName: '信号边角',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '',
        summary: '把路线、风向和停留时间直接写进正文里，封面负责情绪，正文负责把人带回现场。',
        articleTemplate: 'diffuse',
        articleFontPreset: 'clean',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '',
          intro: '傍晚进站前，我把最后一段光线记在票根背面。',
          heading: '把信息写进气氛',
          sectionBody: '当标题被故意留白，读者会更快进入那一段真正有质感的叙述。',
          conclusion: '对这类分发样本来说，封面先建立气氛，正文再慢慢交代发生了什么。',
          imageUrl:
              'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
          imageLayout: 'wrapRight',
          caption: '暮色记录',
        ),
        coverUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        likeCount: 613,
        commentCount: 28,
        shareCount: 35,
        createdAt: '2026-01-05T21:10:00Z',
      ),
      _buildArticlePost(
        postId: 'journal_plain_body_only',
        authorId: 'late_walk',
        displayName: '慢走备忘',
        authorAvatarUrl:
            'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        authorBackgroundUrl:
            'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        title: '',
        summary: '没有标题也没有封面，只留下一段完整正文，让内容自己决定这一页该从哪里开始。',
        articleTemplate: 'journal',
        articleFontPreset: 'rounded',
        articleMarkdownSource: _buildArticleMarkdownSource(
          title: '',
          intro: '路口那家旧文具店快打烊时，灯还像一张温吞的便签纸。',
          heading: '从正文开始',
          sectionBody: '有些记录并不需要题目，它们只需要一个足够安静的开头。',
          conclusion: '当排版和纸感足够稳，正文本身就能撑起一张可分发的卡片。',
        ),
        likeCount: 502,
        commentCount: 19,
        shareCount: 21,
        createdAt: '2026-01-04T18:45:00Z',
      ),
    ]),
    targetCount: 24,
    cloneLabel: 'article',
  );
}
