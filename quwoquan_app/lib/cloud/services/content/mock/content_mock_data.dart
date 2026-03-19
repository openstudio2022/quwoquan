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
    'calligraphy': ['c-human-1', 'c1'],
    'pasta': ['c3'],
    'art_1': ['c-human-1', 'circle_photo_01'],
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
    {
      'postId': 'web-dev',
      'contentType': 'article',
      'authorId': 'tech_daily',
      'displayName': 'TechDaily',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200',
      'title': '2024年现代Web开发趋势：从服务端组件到边缘计算',
      'body': '探讨React Server Components如何改变前端架构，以及Edge Runtime带来的性能飞跃。',
      'coverUrl':
          'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
      'mediaUrls': [
        'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
      ],
      'cards': [
        {
          'title': '范式变化',
          'body': '服务端组件把数据获取前移，前端从“拉数据渲染”转向“组合响应流”。',
          'layout': 'half',
          'imageUrl':
              'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
        },
        {
          'title': '边缘部署',
          'body': '计算更靠近用户后，首屏延迟大幅下降，交互稳定性更容易保障。',
          'layout': 'third',
          'imageUrl':
              'https://images.unsplash.com/photo-1518770660439-4636190af475?w=800',
          'caption': '边缘节点覆盖图',
        },
        {
          'title': '团队协作',
          'body': '组件边界更清晰，前后端职责重新划分，项目交付效率提升。',
          'layout': 'full',
        },
      ],
      'likeCount': 1240,
      'commentCount': 56,
      'favoriteCount': 0,
      'shareCount': 89,
      'createdAt': '2026-01-15T08:00:00Z',
    },
    {
      'postId': 'calligraphy',
      'contentType': 'article',
      'authorId': 'mo_yun',
      'displayName': '墨韵',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200',
      'title': '墨韵流芳：汉字书法中的空间美学与精神寄托',
      'body': '在黑与白的交织中，感受传统文化的独特魅力。',
      'coverUrl':
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
      'cards': [
        {
          'title': '起笔与呼吸',
          'body': '书法讲究提按顿挫，线条里的呼吸感来自手腕节奏。',
          'layout': 'half',
          'imageUrl':
              'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
        },
        {
          'title': '留白空间',
          'body': '字与字之间的留白，是视觉平衡与精神张力的关键。',
          'layout': 'third',
          'imageUrl':
              'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800',
        },
        {
          'title': '当代表达',
          'body': '传统笔法与现代版式并不冲突，关键在节制和秩序。',
          'layout': 'full',
          'caption': '作品局部细节',
        },
      ],
      'likeCount': 892,
      'commentCount': 34,
      'favoriteCount': 0,
      'shareCount': 12,
      'createdAt': '2026-01-14T00:00:00Z',
    },
    {
      'postId': 'pasta',
      'contentType': 'article',
      'authorId': 'chef_mario',
      'displayName': 'Chef Mario',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1583394293214-28ded15ee548?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=1200',
      'title': '意式风情：三种经典酱汁的制作秘籍',
      'body': '从博洛尼亚肉酱到罗勒青酱，带你领略正宗意大利风味。',
      'coverUrl':
          'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
      'cards': [
        {
          'title': '博洛尼亚肉酱',
          'body': '慢炖让番茄酸度柔和，牛肉香气层层释放。',
          'layout': 'half',
          'imageUrl':
              'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
        },
        {
          'title': '青酱基底',
          'body': '罗勒、松子与橄榄油的比例决定口感厚度。',
          'layout': 'third',
          'imageUrl':
              'https://images.unsplash.com/photo-1466637574441-749b8f19452f?w=800',
        },
        {
          'title': '奶油白酱',
          'body': '火候要轻，避免过度还原导致口感发腻。',
          'layout': 'full',
          'caption': '装盘示意',
        },
        {'title': '出餐节奏', 'body': '家庭场景建议分锅并行，保证面条口感弹性。', 'layout': 'full'},
      ],
      'likeCount': 2105,
      'commentCount': 142,
      'favoriteCount': 0,
      'shareCount': 304,
      'createdAt': '2026-01-12T00:00:00Z',
    },
    {
      'postId': 'art_1',
      'contentType': 'article',
      'authorId': 'design_guru',
      'displayName': 'DesignGuru',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
      'authorBackgroundUrl':
          'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=1200',
      'title': 'UI设计的心理学原理：色彩、布局与用户认知',
      'body': '为什么某些配色能让人产生购买欲？深入解析设计背后的心理学机制。',
      'coverUrl':
          'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800',
      'cards': [
        {
          'title': '色彩心理',
          'body': '高饱和冷色常用于理性、科技和专业感塑造。',
          'layout': 'half',
          'imageUrl':
              'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800',
        },
        {
          'title': '布局节奏',
          'body': '信息密度过高会制造疲劳，层级留白决定阅读效率。',
          'layout': 'third',
          'imageUrl':
              'https://images.unsplash.com/photo-1467232004584-a241de8bcf5d?w=800',
        },
        {'title': '认知负担', 'body': '统一交互语言可显著减少切换成本，提升沉浸感。', 'layout': 'full'},
        {
          'title': '商业转化',
          'body': '视觉系统不是装饰，而是用户决策路径的一部分。',
          'layout': 'full',
          'caption': '设计评审样例',
        },
      ],
      'likeCount': 3200,
      'commentCount': 120,
      'favoriteCount': 0,
      'shareCount': 450,
      'createdAt': '2026-01-15T05:00:00Z',
    },
  ]);
}
