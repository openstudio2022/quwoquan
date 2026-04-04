// ignore_for_file: prefer_single_quotes
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';

/// 内容域 mock 数据（canonical 字段，与 FeedItemDto schema 严格对齐）。
///
/// 字段命名以 _projections/discovery_feed.yaml client_projection 为权威：
/// - authorId / displayName / avatarUrl（扁平，无嵌套 user/author sub-map）
/// - coverUrl / thumbnailUrl / imageUrls / videoUrl（media 规范化）
/// - likeCount / commentCount / favoriteCount / shareCount（count 后缀）
/// - body / title（正文 / 标题）
/// - createdAt（ISO 8601）
///
/// 注意：FeedItemDto.fromMap 会通过 alias 兼容旧字段名，此文件只写 canonical 名。
class ContentMockData {
  ContentMockData._();

  static final Map<String, String> _circleNameById = {
    for (final circle in CircleMockData.circles)
      circle['id']?.toString() ?? '': circle['name']?.toString() ?? '',
  };

  static const Map<String, List<String>> _circleIdsByPostId = {
    'd1': ['circle_photo_01', 'c1'],
    'd2': ['c2', 'c-car-2'],
    'd4': ['c1', 'c-human-1'],
    'd5': ['circle_photo_01'],
    'd6': ['c2'],
    'd10': ['c-human-1'],
    'd11': ['circle_photo_01', 'c-tech-admin'],
    'd12': ['c2', 'c-meet-2'],
    'd13': ['c1'],
    'd14': ['circle_photo_01', 'c-human-1'],
    'v1': ['c-meet-1', 'c-meet-2'],
    'v2': ['circle_photo_01'],
    'v3': ['c-tech-admin'],
    'm1': ['c-meet-1'],
    'm2': ['c2', 'c-car-2'],
    'm3': ['c-tech-admin', 'c-human-1'],
    'm4': ['circle_photo_01'],
    'web-dev': ['c-tech-admin'],
    'tech_plain': ['c-tech-admin'],
    'calligraphy': ['c-human-1', 'c1'],
    'ritual_plain': ['c-human-1'],
    'pasta': ['c3'],
    'gentle_plain': ['c3'],
    'art_1': ['c-human-1', 'circle_photo_01'],
    'diffuse_plain': ['c1'],
    'diffuse_cover_body_only': ['c1', 'c-human-1'],
    'journal_cover': ['c2'],
    'journal_plain': ['c2'],
    'journal_plain_body_only': ['c2'],
  };

  static List<Map<String, dynamic>> _withCircleContext(
    List<Map<String, dynamic>> items,
  ) {
    return items
        .map((item) {
          final postId = item['postId']?.toString() ?? '';
          final configuredCircleIds = _circleIdsByPostId[postId];
          if (configuredCircleIds == null || configuredCircleIds.isEmpty) {
            return item;
          }
          final circleNames = configuredCircleIds
              .map((id) => _circleNameById[id] ?? '')
              .where((name) => name.isNotEmpty)
              .toList(growable: false);
          return <String, dynamic>{
            ...item,
            'circleIds': configuredCircleIds,
            'circleNames': circleNames,
            'circleSummaries': [
              for (var i = 0; i < configuredCircleIds.length; i++)
                {
                  'id': configuredCircleIds[i],
                  'name': i < circleNames.length
                      ? circleNames[i]
                      : configuredCircleIds[i],
                },
            ],
            if (configuredCircleIds.isNotEmpty)
              'circleId': configuredCircleIds.first,
            if (circleNames.isNotEmpty) 'circleName': circleNames.first,
          };
        })
        .toList(growable: false);
  }

  static Map<String, dynamic> _buildArticleDocument({
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
    required Map<String, dynamic> articleDocument,
    required int likeCount,
    required int commentCount,
    required int favoriteCount,
    required int shareCount,
    required String createdAt,
    String coverUrl = '',
  }) {
    final normalizedCoverUrl = coverUrl.trim();
    return <String, dynamic>{
      'postId': postId,
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': authorId,
      'displayName': displayName,
      'authorAvatarUrl': authorAvatarUrl,
      'authorBackgroundUrl': authorBackgroundUrl,
      'title': title,
      'body': summary,
      'summary': summary,
      if (normalizedCoverUrl.isNotEmpty) 'coverUrl': normalizedCoverUrl,
      if (normalizedCoverUrl.isNotEmpty) 'thumbnailUrl': normalizedCoverUrl,
      if (normalizedCoverUrl.isNotEmpty)
        'mediaUrls': <String>[normalizedCoverUrl],
      'articleTemplate': articleTemplate,
      'articleFontPreset': articleFontPreset,
      'articlePresentationVersion': 1,
      'articleDocument': articleDocument,
      'likeCount': likeCount,
      'commentCount': commentCount,
      'favoriteCount': favoriteCount,
      'shareCount': shareCount,
      'createdAt': createdAt,
    };
  }

  // ─── Photo feed（美图 tab）─────────────────────────────────────────────────

  // width/height：主图尺寸（px），用于前端直接计算宽高比，无需请求图片元数据。
  // 比例来源于 Unsplash 图片的真实宽高比。
  // authorBackgroundUrl：作者主页背景图，每个作者 ID 固定一张。
  static List<Map<String, dynamic>>
  get discoveryPhotoData => _withCircleContext([
    {
      'postId': 'd1',
      'contentType': 'image',
      'authorId': 'nature_photographer',
      'displayName': '自然摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1518152006812-edab29b069ac?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1518152006812-edab29b069ac?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1518152006812-edab29b069ac?w=800',
        'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800',
      ],
      'width': 960,
      'height': 800,
      'likeCount': 1200,
      'commentCount': 45,
      'favoriteCount': 230,
      'shareCount': 18,
      'createdAt': '2025-12-20T10:00:00Z',
    },
    {
      'postId': 'd2',
      'contentType': 'image',
      'authorId': 'travel_photographer',
      'displayName': '旅行摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800',
      ],
      'width': 640,
      'height': 800,
      'likeCount': 890,
      'commentCount': 32,
      'favoriteCount': 140,
      'shareCount': 25,
      'createdAt': '2025-12-19T15:30:00Z',
    },
    {
      'postId': 'd4',
      'contentType': 'image',
      'authorId': 'street_photo',
      'displayName': '街头摄影',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800',
        'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
        'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=800',
      ],
      'width': 800,
      'height': 800,
      'likeCount': 2300,
      'commentCount': 78,
      'favoriteCount': 510,
      'shareCount': 67,
      'createdAt': '2025-12-18T08:00:00Z',
    },
    {
      'postId': 'd5',
      'contentType': 'image',
      'authorId': 'nature_photographer',
      'displayName': '自然摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
      ],
      'width': 1200,
      'height': 800,
      'likeCount': 1800,
      'commentCount': 56,
      'favoriteCount': 340,
      'shareCount': 42,
      'createdAt': '2025-12-17T12:00:00Z',
    },
    {
      'postId': 'd6',
      'contentType': 'image',
      'authorId': 'travel_photographer',
      'displayName': '旅行摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=800',
      ],
      'width': 800,
      'height': 1067,
      'likeCount': 650,
      'commentCount': 21,
      'favoriteCount': 90,
      'shareCount': 14,
      'createdAt': '2025-12-16T09:20:00Z',
    },
    {
      'postId': 'd10',
      'contentType': 'image',
      'authorId': 'street_photo',
      'displayName': '街头摄影',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1500673922987-e212871fec22?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1500673922987-e212871fec22?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1500673922987-e212871fec22?w=800',
      ],
      'width': 1200,
      'height': 800,
      'likeCount': 430,
      'commentCount': 15,
      'favoriteCount': 60,
      'shareCount': 8,
      'createdAt': '2025-12-15T14:00:00Z',
    },
    {
      'postId': 'd11',
      'contentType': 'image',
      'authorId': 'nature_photographer',
      'displayName': '自然摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1493863641943-9b68992a8d07?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1493863641943-9b68992a8d07?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1493863641943-9b68992a8d07?w=800',
      ],
      'width': 800,
      'height': 534,
      'likeCount': 920,
      'commentCount': 38,
      'favoriteCount': 175,
      'shareCount': 27,
      'createdAt': '2025-12-14T11:30:00Z',
    },
    {
      'postId': 'd12',
      'contentType': 'image',
      'authorId': 'travel_photographer',
      'displayName': '旅行摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1504198458649-3128b932f49e?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1504198458649-3128b932f49e?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1504198458649-3128b932f49e?w=800',
      ],
      'width': 800,
      'height': 600,
      'likeCount': 1100,
      'commentCount': 44,
      'favoriteCount': 200,
      'shareCount': 33,
      'createdAt': '2025-12-13T16:00:00Z',
    },
    {
      'postId': 'd13',
      'contentType': 'image',
      'authorId': 'street_photo',
      'displayName': '街头摄影',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
      ],
      'width': 800,
      'height': 534,
      'likeCount': 780,
      'commentCount': 29,
      'favoriteCount': 115,
      'shareCount': 19,
      'createdAt': '2025-12-12T08:45:00Z',
    },
    {
      'postId': 'd14',
      'contentType': 'image',
      'authorId': 'nature_photographer',
      'displayName': '自然摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800',
      ],
      'width': 1200,
      'height': 800,
      'likeCount': 1560,
      'commentCount': 62,
      'favoriteCount': 290,
      'shareCount': 48,
      'createdAt': '2025-12-11T10:00:00Z',
    },
  ]);

  // ─── Video feed（视频 tab）─────────────────────────────────────────────────
  // width/height：视频分辨率（px），处理管道写入。
  // 竖屏短视频通常为 1080×1920，横屏为 1920×1080。

  static List<Map<String, dynamic>>
  get discoveryVideoData => _withCircleContext([
    {
      'postId': 'v1',
      'contentType': 'video',
      'authorId': 'a1',
      'displayName': '楹语小筑',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=800',
      'videoUrl': 'https://example.com/mock/v1.mp4',
      'body': '东京凌晨两点的街道，有一种难以言喻的孤独美。#治愈系 #东京之夜 #氛围感',
      'width': 1080,
      'height': 1920,
      'likeCount': 12500,
      'commentCount': 892,
      'favoriteCount': 0,
      'shareCount': 1200,
      'durationMs': 45000,
      'musicName': 'Tokyo Midnight Lofi',
      'createdAt': '2026-01-10T02:00:00Z',
    },
    {
      'postId': 'v2',
      'contentType': 'video',
      'authorId': 'a2',
      'displayName': '自然摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1440342359743-84fcb8c21f21?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=800',
      'videoUrl': 'https://example.com/mock/v2.mp4',
      'body': '在大自然中找回内心的平静。🌲✨ #森林漫步 #自然景观 #心灵治愈',
      'width': 1080,
      'height': 1920,
      'likeCount': 8200,
      'commentCount': 430,
      'favoriteCount': 0,
      'shareCount': 560,
      'durationMs': 15000,
      'musicName': 'Forest Whispers',
      'createdAt': '2026-01-09T10:30:00Z',
    },
    {
      'postId': 'v3',
      'contentType': 'video',
      'authorId': 'a3',
      'displayName': '未来科技',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200',
      'coverUrl':
          'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800',
      'videoUrl': 'https://example.com/mock/v3.mp4',
      'body': '2026年，我们的生活将如何被AI改变？一分钟带你了解。#科技趋势 #未来已来',
      'width': 1920,
      'height': 1080,
      'likeCount': 45000,
      'commentCount': 3400,
      'favoriteCount': 0,
      'shareCount': 12000,
      'durationMs': 59000,
      'musicName': 'Digital Future Beats',
      'createdAt': '2026-01-08T20:00:00Z',
    },
  ]);

  // ─── Moment feed（微趣 tab）───────────────────────────────────────────────

  static List<Map<String, dynamic>>
  get discoveryMomentData => _withCircleContext([
    {
      'postId': 'm4',
      'contentType': 'micro',
      'authorId': 'u4',
      'displayName': '李想',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200',
      'body':
          '看他飞奔下车的样子，真帅！如果谁能联系上车主，能不能帮我转告一下，我可不可以去请他吃个饭？ //@理想汽车:点赞每一份挺身而出的勇气！',
      'likeCount': 1581,
      'commentCount': 301,
      'favoriteCount': 0,
      'shareCount': 112,
      'createdAt': '2026-01-15T10:00:00Z',
    },
    {
      'postId': 'm1',
      'contentType': 'micro',
      'authorId': 'u1',
      'displayName': '你的皮炎有点辣',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=1200',
      'body': '左边是董宇辉的办公室，右边是俞敏洪的办公室，说明什么？',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1566699270403-3f7e3f340664?w=600',
        'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=600',
      ],
      'likeCount': 234,
      'commentCount': 36,
      'favoriteCount': 0,
      'shareCount': 4,
      'createdAt': '2026-01-14T10:56:00Z',
    },
    {
      'postId': 'm2',
      'contentType': 'micro',
      'authorId': 'u2',
      'displayName': '仅分组可见',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1432888498266-38ffec3eaf0a?w=1200',
      'body': '最害怕的事情还是发生了，船过去了船夫没赶上……',
      'coverUrl':
          'https://images.unsplash.com/photo-1736171545084-301185012571?w=450',
      'videoUrl':
          'https://images.unsplash.com/photo-1736171545084-301185012571?w=450',
      'durationMs': 15000,
      'likeCount': 452,
      'commentCount': 18,
      'favoriteCount': 0,
      'shareCount': 37,
      'createdAt': '2026-01-13T00:00:00Z',
    },
    {
      'postId': 'm3',
      'contentType': 'micro',
      'authorId': 'u3',
      'displayName': '原价帝吧',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200',
      'body':
          '只要我不尴尬，尴尬的就是别人——投资金银的侃爷Kanye West和妻子比安卡 Bianca Censori 出镜混剪📷 #金银V型反转##黄金#',
      'mediaUrls': List<String>.generate(
        9,
        (i) =>
            'https://images.unsplash.com/photo-1762343290960-74b50d205fb8?w=300&q=80&sig=$i',
      ),
      'likeCount': 1560,
      'commentCount': 420,
      'favoriteCount': 0,
      'shareCount': 89,
      'createdAt': '2026-01-12T08:00:00Z',
    },
  ]);

  // ─── Article feed（文章 tab）──────────────────────────────────────────────

  static List<Map<String, dynamic>>
  get discoveryArticleData => _withCircleContext([
    _buildArticlePost(
      postId: 'web-dev',
      authorId: 'tech_daily',
      displayName: 'TechDaily',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200',
      title: '2024年现代Web开发趋势：从服务端组件到边缘计算',
      summary: '服务端组件把获取数据前移，Edge Runtime 让首屏和交互都更轻更快。',
      articleTemplate: 'tech',
      articleFontPreset: 'mono',
      articleDocument: _buildArticleDocument(
        title: '2024年现代Web开发趋势：从服务端组件到边缘计算',
        intro: '服务端组件正在把前端从“先拿数据再渲染”改写成“边生成边送达”。',
        heading: '范式切换',
        sectionBody: '当数据和组件在同一侧拼装，团队就能把耗时工作前移到响应流之前。',
        conclusion: '真正的竞争力不是概念堆叠，而是把复杂性稳定地收敛在交付链路里。',
        imageUrl:
            'https://images.unsplash.com/photo-1518770660439-4636190af475?w=800',
        imageLayout: 'wrapRight',
        caption: '边缘节点覆盖图',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
      likeCount: 1240,
      commentCount: 56,
      favoriteCount: 0,
      shareCount: 89,
      createdAt: '2026-01-15T08:00:00Z',
    ),
    _buildArticlePost(
      postId: 'calligraphy',
      authorId: 'mo_yun',
      displayName: '墨韵',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200',
      title: '墨韵流芳：汉字书法中的空间美学与精神寄托',
      summary: '在黑与白的克制之间，真正被书写出来的是节奏、呼吸与精神张力。',
      articleTemplate: 'ritual',
      articleFontPreset: 'classic',
      articleDocument: _buildArticleDocument(
        title: '墨韵流芳：汉字书法中的空间美学与精神寄托',
        intro: '书法之美，从来不只是线条本身，而是线条与留白共同构成的秩序。',
        heading: '起笔与呼吸',
        sectionBody: '提按顿挫里的停留感，决定了一幅作品是否拥有“气口”和韵律。',
        conclusion: '当代排版若能保留这种呼吸，传统精神便会自然落进今天的阅读里。',
        imageUrl:
            'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800',
        imageLayout: 'wrapLeft',
        caption: '纸墨细节',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
      likeCount: 892,
      commentCount: 34,
      favoriteCount: 0,
      shareCount: 12,
      createdAt: '2026-01-14T00:00:00Z',
    ),
    _buildArticlePost(
      postId: 'pasta',
      authorId: 'chef_mario',
      displayName: 'Chef Mario',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1583394293214-28ded15ee548?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=1200',
      title: '意式风情：三种经典酱汁的制作秘籍',
      summary: '从红酱到白酱，决定一盘面条记忆点的，是火候与节奏的控制。',
      articleTemplate: 'gentle',
      articleFontPreset: 'rounded',
      articleDocument: _buildArticleDocument(
        title: '意式风情：三种经典酱汁的制作秘籍',
        intro: '一盘看似简单的意面，真正的层次往往藏在酱汁的时间管理里。',
        heading: '火候与浓度',
        sectionBody: '慢炖让番茄的尖锐酸感被柔化，奶香与香草会在最后阶段完成收口。',
        conclusion: '家庭厨房最值得守住的是“不过度”，让每一种味道都留有余地。',
        imageUrl:
            'https://images.unsplash.com/photo-1466637574441-749b8f19452f?w=800',
        imageLayout: 'fullWidth',
        caption: '装盘示意',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
      likeCount: 2105,
      commentCount: 142,
      favoriteCount: 0,
      shareCount: 304,
      createdAt: '2026-01-12T00:00:00Z',
    ),
    _buildArticlePost(
      postId: 'art_1',
      authorId: 'design_guru',
      displayName: 'DesignGuru',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=1200',
      title: 'UI设计的心理学原理：色彩、布局与用户认知',
      summary: '视觉系统不是装饰，色彩和留白本质上都在影响用户的决策速度。',
      articleTemplate: 'diffuse',
      articleFontPreset: 'clean',
      articleDocument: _buildArticleDocument(
        title: 'UI设计的心理学原理：色彩、布局与用户认知',
        intro: '用户对界面的第一判断，往往在阅读前就已经开始。',
        heading: '色彩心理',
        sectionBody: '高饱和冷色常被感知为理性和科技，暖色则更容易制造行动冲动。',
        conclusion: '一套有效的视觉语言，关键不在堆叠细节，而在让路径更容易被理解。',
        imageUrl:
            'https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=800',
        imageLayout: 'wrapLeft',
        caption: '设计评审样例',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800',
      likeCount: 3200,
      commentCount: 120,
      favoriteCount: 0,
      shareCount: 450,
      createdAt: '2026-01-15T05:00:00Z',
    ),
    _buildArticlePost(
      postId: 'journal_cover',
      authorId: 'travel_note',
      displayName: '山川手账',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=1200',
      title: '一座山的晨雾：把徒步记成一本可以翻页的手账',
      summary: '旅行不是景点清单，而是一连串被光线、气味和脚步慢慢浸透的感受。',
      articleTemplate: 'journal',
      articleFontPreset: 'handwritten',
      articleDocument: _buildArticleDocument(
        title: '一座山的晨雾：把徒步记成一本可以翻页的手账',
        intro: '凌晨出发时，山路还裹着湿气，鞋底踩下去像踩进一页没晒干的纸。',
        heading: '边走边贴',
        sectionBody: '把票据、路线、海拔和一句突然冒出的心情都贴进同一页，旅程就有了体温。',
        conclusion: '好的手账从不追求完整，它只保留那些会在很久之后再次把人带回去的瞬间。',
        imageUrl:
            'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=800',
        imageLayout: 'wrapRight',
        caption: '晨雾扉页',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=800',
      likeCount: 1460,
      commentCount: 61,
      favoriteCount: 0,
      shareCount: 88,
      createdAt: '2026-01-11T07:20:00Z',
    ),
    _buildArticlePost(
      postId: 'tech_plain',
      authorId: 'infra_log',
      displayName: 'InfraLog',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200',
      title: '从日志到观测：团队如何为真实故障建立共同语言',
      summary: '真正有效的观测不是面板越多越好，而是每个角色都能找到自己的判断入口。',
      articleTemplate: 'tech',
      articleFontPreset: 'clean',
      articleDocument: _buildArticleDocument(
        title: '从日志到观测：团队如何为真实故障建立共同语言',
        intro: '故障发生时最昂贵的不是恢复时间，而是团队对“问题正在发生什么”没有共同理解。',
        heading: '事件对齐',
        sectionBody: '把日志、指标和 tracing 串在同一语义下，排障链路才不会被多套命名撕裂。',
        conclusion: '观测最终服务的是决策速度，而不是仪表盘本身的复杂程度。',
        imageUrl:
            'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800',
        imageLayout: 'wrapRight',
        caption: '监控面板草图',
      ),
      likeCount: 980,
      commentCount: 42,
      favoriteCount: 0,
      shareCount: 61,
      createdAt: '2026-01-10T09:00:00Z',
    ),
    _buildArticlePost(
      postId: 'ritual_plain',
      authorId: 'ink_house',
      displayName: '纸上居',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1500534623283-312aade485b7?w=1200',
      title: '雨夜读帖：为什么东方手卷总能让人慢下来',
      summary: '慢不是效率的反义词，而是一种把注意力重新还给阅读对象的方式。',
      articleTemplate: 'ritual',
      articleFontPreset: 'classic',
      articleDocument: _buildArticleDocument(
        title: '雨夜读帖：为什么东方手卷总能让人慢下来',
        intro: '展开手卷时，视线被主动限制在一小段距离里，速度因此自然被放缓。',
        heading: '节奏控制',
        sectionBody: '纸张纹理、行距和墨色密度一起把阅读的呼吸感重新带了回来。',
        conclusion: '当媒介本身参与叙事，阅读就不只是理解信息，而是进入一种状态。',
        imageUrl:
            'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=800',
        imageLayout: 'wrapLeft',
        caption: '卷页细节',
      ),
      likeCount: 730,
      commentCount: 26,
      favoriteCount: 0,
      shareCount: 18,
      createdAt: '2026-01-09T19:30:00Z',
    ),
    _buildArticlePost(
      postId: 'gentle_plain',
      authorId: 'home_writer',
      displayName: '慢慢生活',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1511988617509-a57c8a288659?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=1200',
      title: '把周末过成一页柔软的家居笔记',
      summary: '家并不需要每天焕新，真正改变气氛的是一些安静但持续的微调。',
      articleTemplate: 'gentle',
      articleFontPreset: 'clean',
      articleDocument: _buildArticleDocument(
        title: '把周末过成一页柔软的家居笔记',
        intro: '窗帘被换成更透光的材质后，客厅在下午会像一张慢慢被晒暖的纸。',
        heading: '轻调整',
        sectionBody: '靠枕、香气、桌面杂物和灯光色温的微调，比一次性大改造更能改变居住体感。',
        conclusion: '生活质感不总来自昂贵物件，更多时候来自对日常节奏的认真照顾。',
        imageUrl:
            'https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800',
        imageLayout: 'wrapLeft',
        caption: '窗边一角',
      ),
      likeCount: 1186,
      commentCount: 74,
      favoriteCount: 0,
      shareCount: 103,
      createdAt: '2026-01-08T12:15:00Z',
    ),
    _buildArticlePost(
      postId: 'diffuse_plain',
      authorId: 'visual_lab',
      displayName: '视觉实验室',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=1200',
      title: '把留白做成节奏：信息界面里的“呼吸设计”',
      summary: '所谓高级感并不是更空，而是让信息的停顿和推进都变得可预测。',
      articleTemplate: 'diffuse',
      articleFontPreset: 'clean',
      articleDocument: _buildArticleDocument(
        title: '把留白做成节奏：信息界面里的“呼吸设计”',
        intro: '当内容变多，留白真正承担的职责是让用户愿意继续往下看。',
        heading: '节奏设计',
        sectionBody: '留白不只是空着，它和字号、段落密度、卡片间距一起决定了浏览阻力。',
        conclusion: '界面一旦会呼吸，用户就更容易把注意力留在信息本身，而不是控件噪音上。',
        imageUrl:
            'https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=800',
        imageLayout: 'wrapRight',
        caption: '版式网格',
      ),
      likeCount: 1540,
      commentCount: 67,
      favoriteCount: 0,
      shareCount: 95,
      createdAt: '2026-01-07T18:40:00Z',
    ),
    _buildArticlePost(
      postId: 'journal_plain',
      authorId: 'field_notes',
      displayName: '田野笔记',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=1200',
      title: '城市散步的边角料，如何变成一本值得反复翻的小册子',
      summary: '真正让人想保存下来的，不是完整纪实，而是那些被贴在边角里的细小瞬间。',
      articleTemplate: 'journal',
      articleFontPreset: 'rounded',
      articleDocument: _buildArticleDocument(
        title: '城市散步的边角料，如何变成一本值得反复翻的小册子',
        intro: '一张收据、一段路名和一处树影，就足够撑起一页有情绪的散步记录。',
        heading: '贴纸与证据',
        sectionBody: '当票据、时间、天气和一句突然冒出的感受被并排放下，城市会重新长出层次。',
        conclusion: '好的手账不负责证明你去了哪里，它负责提醒你当时为什么会想停下来。',
        imageUrl:
            'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
        imageLayout: 'wrapRight',
        caption: '散步拾片',
      ),
      likeCount: 865,
      commentCount: 39,
      favoriteCount: 0,
      shareCount: 44,
      createdAt: '2026-01-06T16:05:00Z',
    ),
    _buildArticlePost(
      postId: 'diffuse_cover_body_only',
      authorId: 'signal_notes',
      displayName: '信号边角',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=1200',
      title: '',
      summary: '把路线、风向和停留时间直接写进正文里，封面负责情绪，正文负责把人带回现场。',
      articleTemplate: 'diffuse',
      articleFontPreset: 'clean',
      articleDocument: _buildArticleDocument(
        title: '',
        intro: '傍晚进站前，我把最后一段光线记在票根背面。',
        heading: '把信息写进气氛',
        sectionBody: '当标题被故意留白，读者会更快进入那一段真正有质感的叙述。',
        conclusion: '对这类分发样本来说，封面先建立气氛，正文再慢慢交代发生了什么。',
        imageUrl:
            'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=800',
        imageLayout: 'wrapRight',
        caption: '暮色记录',
      ),
      coverUrl:
          'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=800',
      likeCount: 613,
      commentCount: 28,
      favoriteCount: 0,
      shareCount: 35,
      createdAt: '2026-01-05T21:10:00Z',
    ),
    _buildArticlePost(
      postId: 'journal_plain_body_only',
      authorId: 'late_walk',
      displayName: '慢走备忘',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1517081052940-3619a36f1a53?w=1200',
      title: '',
      summary: '没有标题也没有封面，只留下一段完整正文，让内容自己决定这一页该从哪里开始。',
      articleTemplate: 'journal',
      articleFontPreset: 'rounded',
      articleDocument: _buildArticleDocument(
        title: '',
        intro: '路口那家旧文具店快打烊时，灯还像一张温吞的便签纸。',
        heading: '从正文开始',
        sectionBody: '有些记录并不需要题目，它们只需要一个足够安静的开头。',
        conclusion: '当排版和纸感足够稳，正文本身就能撑起一张可分发的卡片。',
      ),
      likeCount: 502,
      commentCount: 19,
      favoriteCount: 0,
      shareCount: 21,
      createdAt: '2026-01-04T18:45:00Z',
    ),
  ]);

  static List<Map<String, dynamic>>
  get articleCanonicalFallbackFixtures => <Map<String, dynamic>>[
    _buildArticlePost(
      postId: 'article_document_only_fixture',
      authorId: 'article_fixture_writer',
      displayName: '旧稿修复',
      authorAvatarUrl:
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      authorBackgroundUrl:
          'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200',
      title: '连续文档优先',
      summary: '只保留 articleDocument 的旧稿，用于验证 canonical 优先级。',
      articleTemplate: 'journal',
      articleFontPreset: 'handwritten',
      articleDocument: _buildArticleDocument(
        title: '连续文档优先',
        intro: '旧稿只剩下一份连续文档，但阅读链路仍应完整恢复。',
        heading: '恢复顺序',
        sectionBody:
            '当 blocks、cards 与 body 缺席时，reader 应优先从 articleDocument 恢复内容。',
        conclusion: '只要 canonical 还在，旧数据就不该失去阅读能力。',
        imageUrl:
            'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800',
        imageLayout: 'wrapRight',
        caption: '恢复样本',
      ),
      likeCount: 40,
      commentCount: 4,
      favoriteCount: 0,
      shareCount: 2,
      createdAt: '2026-01-05T10:00:00Z',
    ),
    <String, dynamic>{
      'postId': 'article_blocks_only_fixture',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'article_fixture_writer',
      'displayName': '旧稿修复',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      'title': '语义块回退',
      'articleTemplate': 'tech',
      'articleFontPreset': 'mono',
      'articlePresentationVersion': 1,
      'articleBlocks': <Map<String, dynamic>>[
        {'id': 'p0', 'type': 'paragraph', 'text': '旧 blocks 仍要读得出来。'},
        {'id': 'h2', 'type': 'heading2', 'text': '块级恢复'},
        {
          'id': 'img',
          'type': 'image',
          'imagePath':
              'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
          'imageLayout': 'wrapLeft',
        },
        {'id': 'p1', 'type': 'paragraph', 'text': '图片与文字的相对顺序必须保住。'},
      ],
      'createdAt': '2026-01-05T09:00:00Z',
      'likeCount': 22,
      'commentCount': 3,
      'favoriteCount': 0,
      'shareCount': 1,
    },
    <String, dynamic>{
      'postId': 'article_cards_only_fixture',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'article_fixture_writer',
      'displayName': '旧稿修复',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      'title': '卡片回退',
      'body': '',
      'articleTemplate': 'gentle',
      'articleFontPreset': 'clean',
      'articlePresentationVersion': 1,
      'cards': <Map<String, dynamic>>[
        {
          'title': '第一节',
          'body': '旧 cards 结构仍需转成连续阅读 section。',
          'imageUrl':
              'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
        },
      ],
      'createdAt': '2026-01-05T08:00:00Z',
      'likeCount': 18,
      'commentCount': 2,
      'favoriteCount': 0,
      'shareCount': 1,
    },
    <String, dynamic>{
      'postId': 'article_body_only_fixture',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'article_fixture_writer',
      'displayName': '旧稿修复',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      'title': '正文回退',
      'body': '当只有 body 存在时，也应至少生成一段可阅读的正文。',
      'articleTemplate': 'diffuse',
      'articleFontPreset': 'clean',
      'articlePresentationVersion': 1,
      'createdAt': '2026-01-05T07:00:00Z',
      'likeCount': 10,
      'commentCount': 1,
      'favoriteCount': 0,
      'shareCount': 0,
    },
  ];
}
