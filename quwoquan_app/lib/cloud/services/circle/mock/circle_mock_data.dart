import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_file_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_member_roster_item_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_stats_wire_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// 圈子域 Mock 数据（从 PrototypeMockData 搬迁）
///
/// 列表/索引真源为 [catalogCircleDtos] / [primaryCircleDto]；[_catalogCircleWires] /
/// [_primaryDetailWire] 仅作字面量 SSOT，经 [CircleDto.fromMap] 派生强类型。
class CircleMockData {
  const CircleMockData._();

  static const String primaryCircleId = 'circle_photo_01';

  static final Map<String, dynamic> _primaryDetailWire = {
    'name': '光影摄影社',
    'id': 'circle_photo_01',
    'ownerId': 'u3',
    'role': 'owner',
    'joinStatus': 'joined',
    'isFollowed': true,
    'avatar':
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
    'cover':
        'https://images.unsplash.com/photo-1493125594441-2da1f5c644f5?q=80&w=1440',
    'coverUrl':
        'https://images.unsplash.com/photo-1493125594441-2da1f5c644f5?q=80&w=1440',
    'desc': '汇聚全球摄影爱好者，分享快门背后的故事。无论你是专业摄影师还是手机摄影爱好者，这里都有你的位置。',
    'description': '汇聚全球摄影爱好者，分享快门背后的故事。无论你是专业摄影师还是手机摄影爱好者，这里都有你的位置。',
    'tags': ['城市漫步', '胶片', '人像', '风光'],
    'visibility': 'public',
    'joinPolicy': 'approval',
    'categoryId': 'humanity',
    'subCategory': '影像',
    'memberCount': 128,
    'postCount': 1024,
    'weeklyActiveCount': 45,
    'conversationId': 'conv_circle_photo_01',
    'domainId': 'culture_arts',
    'autoSyncChat': true,
    'storageUsedBytes': 52428800,
    'storageQuotaBytes': 1073741824,
    'sectionConfig': [
      {
        'sectionType': 'works',
        'visible': true,
        'order': 0,
        'customTitle': null,
      },
      {'sectionType': 'chat', 'visible': true, 'order': 1, 'customTitle': null},
      {
        'sectionType': 'storage',
        'visible': true,
        'order': 2,
        'customTitle': null,
      },
      {
        'sectionType': 'interaction',
        'visible': true,
        'order': 3,
        'customTitle': null,
      },
    ],
    'stats': {
      'members': '128',
      'groups': '26',
      'fans': '45.2k',
      'likes': '128k',
    },
    'hasNewMessages': true,
  };

  static Map<String, dynamic> get circleInfo =>
      Map<String, dynamic>.from(_primaryDetailWire);

  static final List<Map<String, dynamic>> _catalogCircleWires = [
    {
      'id': 'c1',
      'name': '极简摄影俱乐部',
      'coverUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600',
      'cover':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600',
      'avatar':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600',
      'desc': '少即是多，用减法看世界',
      'memberCount': 2340,
      'postCount': 128,
      'domainId': 'culture_arts',
      'categoryId': 'humanity',
      'subCategory': '影像',
    },
    {
      'id': 'c2',
      'name': '旅行手账',
      'coverUrl':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
      'cover':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
      'avatar':
          'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600',
      'desc': '记录脚下的每一寸土地',
      'memberCount': 1280,
      'postCount': 56,
      'domainId': 'culture_arts',
      'categoryId': 'travel',
      'subCategory': '攻略',
    },
    {
      'id': 'c3',
      'name': '咖啡品鉴',
      'coverUrl':
          'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
      'cover':
          'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
      'avatar':
          'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
      'desc': '从豆子到杯子的风味之旅',
      'memberCount': 890,
      'postCount': 34,
      'domainId': 'culture_arts',
      'categoryId': 'food',
      'subCategory': '咖啡',
    },
    {
      'id': 'c-cam-1',
      'name': '上海交大·2020级校友',
      'coverUrl':
          'https://images.unsplash.com/photo-1562774053-701939374585?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1562774053-701939374585?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1562774053-701939374585?q=80&w=400',
      'desc': '思源致远，爱国荣校',
      'memberCount': 1287,
      'categoryId': 'campus',
      'subCategory': '母校',
      'domainId': 'education',
    },
    {
      'id': 'c-cam-2',
      'name': '互联网校友内推圈',
      'coverUrl':
          'https://images.unsplash.com/photo-1522202176988-66273c2fd55f?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1522202176988-66273c2fd55f?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1522202176988-66273c2fd55f?q=80&w=400',
      'desc': '大厂Offer直通车',
      'memberCount': 6543,
      'categoryId': 'campus',
      'subCategory': '职场互助',
      'domainId': 'education',
    },
    {
      'id': 'c-car-1',
      'name': 'Model 3 焕新版·上海车友会',
      'coverUrl':
          'https://images.unsplash.com/photo-1560958089-b8a1929cea89?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1560958089-b8a1929cea89?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1560958089-b8a1929cea89?q=80&w=400',
      'desc': '电车生活，不止于行',
      'memberCount': 2100,
      'categoryId': 'car',
      'subCategory': '品牌',
      'domainId': 'automotive',
    },
    {
      'id': 'c-car-2',
      'name': '周末自驾发现上海',
      'coverUrl':
          'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?q=80&w=400',
      'desc': '逃离城市喧嚣，探索隐秘角落',
      'memberCount': 890,
      'categoryId': 'car',
      'subCategory': '自驾',
      'domainId': 'automotive',
    },
    {
      'id': 'c-meet-1',
      'name': '魔都搭子集合',
      'coverUrl':
          'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?q=80&w=400',
      'desc': '吃饭、看展、运动，万事皆可搭',
      'memberCount': 12345,
      'categoryId': 'meet',
      'subCategory': '搭子',
      'domainId': 'social_meet',
    },
    {
      'id': 'c-meet-2',
      'name': '摄影师线下约拍',
      'coverUrl':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=400',
      'desc': '用镜头定格美好瞬间',
      'memberCount': 3456,
      'categoryId': 'meet',
      'subCategory': '寻友',
      'domainId': 'social_meet',
    },
    {
      'id': 'c-human-1',
      'name': '电影放映室',
      'coverUrl':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1536440136628-849c177e76a1?q=80&w=400',
      'desc': '每周末一部经典老电影',
      'memberCount': 5678,
      'categoryId': 'humanity',
      'subCategory': '影像',
      'domainId': 'culture_arts',
    },
    {
      'id': 'c-photo-owner',
      'name': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
      'desc': '光影之间，皆是故事',
      'memberCount': 128,
      'categoryId': 'humanity',
      'subCategory': '影像',
      'domainId': 'culture_arts',
    },
    {
      'id': 'c-tech-admin',
      'name': 'AI 前沿探索者',
      'coverUrl':
          'https://images.unsplash.com/photo-1677442135136-760c813028c4?q=80&w=400',
      'cover':
          'https://images.unsplash.com/photo-1677442135136-760c813028c4?q=80&w=400',
      'avatar':
          'https://images.unsplash.com/photo-1677442135136-760c813028c4?q=80&w=400',
      'desc': '拥抱 AGI 时代',
      'memberCount': 9999,
      'categoryId': 'tech',
      'subCategory': 'AI',
      'domainId': 'tech',
    },
  ];

  static Map<String, dynamic> _wireForCircleDto(Map<String, dynamic> raw) {
    final m = Map<String, dynamic>.from(raw);
    m.putIfAbsent('ownerId', () => 'mock_owner');
    m.putIfAbsent('createdAt', () => '2020-01-01T00:00:00.000Z');
    m.putIfAbsent('updatedAt', () => '2020-01-01T00:00:00.000Z');
    return m;
  }

  static List<CircleDto>? _catalogCircleDtosCache;
  static List<CircleDto> get catalogCircleDtos {
    return _catalogCircleDtosCache ??= [
      for (final w in _catalogCircleWires)
        CircleDto.fromMap(_wireForCircleDto(w)),
    ];
  }

  static CircleDto? _primaryCircleDtoCache;
  static CircleDto get primaryCircleDto {
    return _primaryCircleDtoCache ??= CircleDto.fromMap(
      _wireForCircleDto(_primaryDetailWire),
    );
  }

  /// 与 [MockCircleRepository] 初始列表一致（同 id 后写覆盖，顺序为插入序）。
  static List<CircleDto> buildRepositorySeedCircleDtos() {
    final map = <String, CircleDto>{};
    void put(CircleDto d) {
      map[d.id] = d;
    }

    put(primaryCircleDto);
    for (final d in catalogCircleDtos) {
      put(d);
    }
    return map.values.toList(growable: true);
  }

  static CircleDto? tryResolveCircleDto(String id) {
    final trimmed = id.trim();
    if (trimmed.isEmpty) return null;
    if (trimmed == primaryCircleId) return primaryCircleDto;
    for (final c in catalogCircleDtos) {
      if (c.id == trimmed) return c;
    }
    return null;
  }

  static List<Map<String, dynamic>> get activities => [
    {
      'id': 'a1',
      'type': 'live',
      'title': '静安寺附近校友连麦：今晚聊聊职场内推',
      'status': 'active',
      'circleId': 'c-cam-2',
      'circleName': '互联网校友内推圈',
      'image':
          'https://images.unsplash.com/photo-1543269865-cbf427effbad?q=80&w=800',
    },
    {
      'id': 'a2',
      'type': 'gathering',
      'title': '【车友招募】周末莫干山自驾游',
      'status': 'upcoming',
      'circleId': 'c-car-1',
      'circleName': 'Model 3 焕新版·上海车友会',
      'image':
          'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?q=80&w=800',
    },
  ];

  /// 成员行真源（[ListCircleMembers] / Mock 富集字段）；[members] wire 由此派生。
  static final List<CircleMemberRosterItemDto> catalogMemberRosterRows = [
    CircleMemberRosterItemDto(
      membershipId: 'u1',
      circleId: '',
      userId: 'u1',
      role: 'member',
      joinedAt: DateTime(2024, 1, 15),
      displayName: '陈一发',
      avatarUrl:
          'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
    ),
    CircleMemberRosterItemDto(
      membershipId: 'u2',
      circleId: '',
      userId: 'u2',
      role: 'admin',
      joinedAt: DateTime(2024, 1, 1),
      displayName: '周杰伦',
      avatarUrl:
          'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=100',
    ),
    CircleMemberRosterItemDto(
      membershipId: 'u3',
      circleId: '',
      userId: 'u3',
      role: 'owner',
      joinedAt: DateTime(2023, 12, 1),
      displayName: '李青云',
      avatarUrl:
          'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
    ),
  ];

  static List<Map<String, dynamic>> get members => catalogMemberRosterRows
      .map(
        (r) => <String, dynamic>{
          'id': r.userId,
          'name': r.displayName,
          'avatar': r.avatarUrl,
          'role': r.role,
          'joinedAt':
              '${r.joinedAt.year.toString().padLeft(4, '0')}-'
              '${r.joinedAt.month.toString().padLeft(2, '0')}-'
              '${r.joinedAt.day.toString().padLeft(2, '0')}',
        },
      )
      .toList(growable: false);

  static final List<Map<String, dynamic>> _fileWireSeeds = [
    {
      'id': 'f1',
      'name': '摄影指南.pdf',
      'fileType': 'file',
      'mimeType': 'application/pdf',
      'sizeBytes': 2097152,
      'uploaderId': 'u3',
      'status': 'active',
      'createdAt': '2024-02-01',
      'updatedAt': '2024-02-01',
    },
    {
      'id': 'f2',
      'name': '器材对比表.xlsx',
      'fileType': 'file',
      'mimeType':
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'sizeBytes': 524288,
      'uploaderId': 'u2',
      'status': 'active',
      'createdAt': '2024-02-10',
      'updatedAt': '2024-02-10',
    },
    {
      'id': 'f3',
      'name': '活动照片',
      'fileType': 'folder',
      'mimeType': null,
      'sizeBytes': 0,
      'uploaderId': 'u1',
      'status': 'active',
      'createdAt': '2024-01-20',
      'updatedAt': '2024-01-20',
    },
  ];

  static List<CircleFileDto>? _catalogCircleFileDtosCache;

  static List<CircleFileDto> get catalogCircleFileDtos {
    return _catalogCircleFileDtosCache ??= [
      for (final w in _fileWireSeeds)
        CircleFileDto.fromMap(Map<String, dynamic>.from(w)),
    ];
  }

  /// 与记录 Mock 一致：不含 `circleId`（由仓库在 [CircleFileDto.fromMap] 时注入）。
  static List<Map<String, dynamic>> get files => catalogCircleFileDtos
      .map((d) {
        final m = Map<String, dynamic>.from(d.toMap());
        m.remove('circleId');
        return m;
      })
      .toList(growable: false);

  static final List<Map<String, dynamic>> _circleFeedWireSeeds = [
    {
      'id': 'circle_post_image_1',
      'postId': 'circle_post_image_1',
      'circleId': 'circle_photo_01',
      'type': 'photo',
      'contentType': 'image',
      'contentIdentity': 'work',
      'authorId': 'u1',
      'authorNickname': '旅行摄影师',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
      'title': '清晨光影练习',
      'body': '第一次踩点就遇到很通透的晨雾，记录下圈友活动前的安静片刻。',
      'circleIds': ['circle_photo_01', 'c1'],
      'circleNames': ['光影摄影社', '极简摄影俱乐部'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c1', 'name': '极简摄影俱乐部'},
      ],
      'circleName': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=900',
      'imageUrls': [
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=900',
      ],
      'likeCount': 342,
      'favoriteCount': 31,
      'shareCount': 12,
    },
    {
      'id': 'circle_post_video_1',
      'postId': 'circle_post_video_1',
      'circleId': 'circle_photo_01',
      'type': 'video',
      'contentType': 'video',
      'contentIdentity': 'work',
      'authorId': 'u2',
      'authorNickname': '城市观察员',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
      'title': '夜色车流延时',
      'body': '圈子活动结束后补了一段桥面延时，准备回去剪一个一分钟短片。',
      'circleIds': ['circle_photo_01', 'c-car-2'],
      'circleNames': ['光影摄影社', '周末自驾发现上海'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c-car-2', 'name': '周末自驾发现上海'},
      ],
      'circleName': '光影摄影社',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=900',
      'videoUrl':
          'https://flutter.github.io/assets-for-api-docs/assets/videos/bee.mp4',
      'likeCount': 211,
      'favoriteCount': 22,
      'shareCount': 18,
    },
    {
      'id': 'circle_post_moment_text_1',
      'postId': 'circle_post_moment_text_1',
      'circleId': 'circle_photo_01',
      'type': 'moment',
      'contentType': 'micro',
      'contentIdentity': 'moment',
      'authorId': 'u3',
      'authorNickname': '阿秋',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
      'title': '临时改地点提醒',
      'body': '今天风有点大，傍晚拍摄集合点改到南门咖啡车旁，先到的圈友可以在群里报个到。',
      'circleIds': ['circle_photo_01', 'c-meet-1'],
      'circleNames': ['光影摄影社', '魔都搭子集合'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c-meet-1', 'name': '魔都搭子集合'},
      ],
      'circleName': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=900',
      'likeCount': 128,
      'favoriteCount': 9,
      'shareCount': 6,
    },
    {
      'id': 'circle_post_note_1',
      'postId': 'circle_post_note_1',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'u4',
      'authorNickname': '构图实验室',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200',
      'title': '雨夜街拍的三种取景思路',
      'body': '把高光控制、路面反射和人物停顿拆开看，文章里整理了这次活动最有用的 3 个构图模板。',
      'circleIds': ['circle_photo_01', 'c-human-1'],
      'circleNames': ['光影摄影社', '午夜电影俱乐部'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c-human-1', 'name': '午夜电影俱乐部'},
      ],
      'circleName': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=900',
      'likeCount': 89,
      'favoriteCount': 14,
      'shareCount': 4,
    },
    {
      'id': 'circle_journal_cover',
      'postId': 'circle_journal_cover',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'u5',
      'authorNickname': '山川手账',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
      'title': '山路晨雾手账：把徒步笔记做成可翻页的旅途册',
      'body': '把路标、票据和雾气里的第一束光整理成一张真正适合在圈子里分发的手账扉页。',
      'summary': '把路标、票据和雾气里的第一束光整理成一张真正适合在圈子里分发的手账扉页。',
      'articleTemplate': 'journal',
      'articleFontPreset': 'handwritten',
      'articlePresentationVersion': 1,
      'circleIds': ['circle_photo_01', 'c2'],
      'circleNames': ['光影摄影社', '旅行手账'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c2', 'name': '旅行手账'},
      ],
      'circleName': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=900',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=900',
      'articleDocument': {
        'title': '山路晨雾手账：把徒步笔记做成可翻页的旅途册',
        'body':
            '凌晨出发时，山路像一张还没晒干的纸。\n把海拔、气温和一句突然冒出的心情都贴进同一页，旅行就有了温度。\n真正值得留下来的，是那些会在很久之后再次把人带回去的瞬间。',
        'blocks': [
          {
            'id': 'circle_journal_cover_p0',
            'type': 'paragraph',
            'text': '凌晨出发时，山路像一张还没晒干的纸。',
          },
          {'id': 'circle_journal_cover_h2', 'type': 'heading2', 'text': '边走边贴'},
          {
            'id': 'circle_journal_cover_img',
            'type': 'image',
            'imageUrl':
                'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=900',
            'imageLayout': 'wrapRight',
            'caption': '晨雾扉页',
          },
          {
            'id': 'circle_journal_cover_p1',
            'type': 'paragraph',
            'text': '把海拔、气温和一句突然冒出的心情都贴进同一页，旅行就有了温度。',
          },
          {
            'id': 'circle_journal_cover_section',
            'type': 'sectionTitle',
            'text': '收束',
          },
          {
            'id': 'circle_journal_cover_p2',
            'type': 'paragraph',
            'text': '真正值得留下来的，是那些会在很久之后再次把人带回去的瞬间。',
          },
        ],
      },
      'likeCount': 164,
      'favoriteCount': 28,
      'shareCount': 11,
    },
    {
      'id': 'circle_ritual_plain',
      'postId': 'circle_ritual_plain',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'u6',
      'authorNickname': '纸上居',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=200',
      'title': '雨夜读帖：为什么东方卷页总能让人慢下来',
      'body': '纸张纹理、行距与墨色密度一起把阅读的呼吸感带了回来，没有封面也能成立为一张完整文字卡。',
      'summary': '纸张纹理、行距与墨色密度一起把阅读的呼吸感带了回来，没有封面也能成立为一张完整文字卡。',
      'articleTemplate': 'ritual',
      'articleFontPreset': 'classic',
      'articlePresentationVersion': 1,
      'circleIds': ['circle_photo_01', 'c-human-1'],
      'circleNames': ['光影摄影社', '电影放映室'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c-human-1', 'name': '电影放映室'},
      ],
      'circleName': '光影摄影社',
      'articleDocument': {
        'title': '雨夜读帖：为什么东方卷页总能让人慢下来',
        'body':
            '展开手卷时，视线被主动限制在一小段距离里。\n纸张纹理、行距与墨色密度一起把阅读的呼吸感带了回来。\n当媒介本身参与叙事，阅读就不只是理解信息，而是进入一种状态。',
        'blocks': [
          {
            'id': 'circle_ritual_plain_p0',
            'type': 'paragraph',
            'text': '展开手卷时，视线被主动限制在一小段距离里。',
          },
          {'id': 'circle_ritual_plain_h2', 'type': 'heading2', 'text': '节奏控制'},
          {
            'id': 'circle_ritual_plain_p1',
            'type': 'paragraph',
            'text': '纸张纹理、行距与墨色密度一起把阅读的呼吸感带了回来。',
          },
          {
            'id': 'circle_ritual_plain_section',
            'type': 'sectionTitle',
            'text': '收束',
          },
          {
            'id': 'circle_ritual_plain_p2',
            'type': 'paragraph',
            'text': '当媒介本身参与叙事，阅读就不只是理解信息，而是进入一种状态。',
          },
        ],
      },
      'likeCount': 117,
      'favoriteCount': 17,
      'shareCount': 6,
    },
    {
      'id': 'circle_diffuse_cover_body_only',
      'postId': 'circle_diffuse_cover_body_only',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'u7',
      'authorNickname': '夜色便签',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
      'title': '',
      'body': '把路线、风向和最后一班地铁时间都塞进一段正文里，封面负责气氛，正文负责把人带回活动现场。',
      'summary': '把路线、风向和最后一班地铁时间都塞进一段正文里，封面负责气氛，正文负责把人带回活动现场。',
      'articleTemplate': 'diffuse',
      'articleFontPreset': 'clean',
      'articlePresentationVersion': 1,
      'circleIds': ['circle_photo_01', 'c-meet-1'],
      'circleNames': ['光影摄影社', '魔都搭子集合'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c-meet-1', 'name': '魔都搭子集合'},
      ],
      'circleName': '光影摄影社',
      'coverUrl':
          'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=900',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=900',
      'articleDocument': {
        'title': '',
        'body':
            '散场前，站台的风比人群更早一步安静下来。\n把路线、风向和末班车时间并排写下，这张卡片就有了真正能回看的信息。\n封面先定住情绪，正文再把那一晚重新讲清楚。',
        'blocks': [
          {
            'id': 'circle_diffuse_cover_body_only_p0',
            'type': 'paragraph',
            'text': '散场前，站台的风比人群更早一步安静下来。',
          },
          {
            'id': 'circle_diffuse_cover_body_only_h2',
            'type': 'heading2',
            'text': '把信息写进气氛',
          },
          {
            'id': 'circle_diffuse_cover_body_only_img',
            'type': 'image',
            'imageUrl':
                'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=900',
            'imageLayout': 'wrapRight',
            'caption': '夜色出站口',
          },
          {
            'id': 'circle_diffuse_cover_body_only_p1',
            'type': 'paragraph',
            'text': '把路线、风向和末班车时间并排写下，这张卡片就有了真正能回看的信息。',
          },
          {
            'id': 'circle_diffuse_cover_body_only_section',
            'type': 'sectionTitle',
            'text': '收束',
          },
          {
            'id': 'circle_diffuse_cover_body_only_p2',
            'type': 'paragraph',
            'text': '封面先定住情绪，正文再把那一晚重新讲清楚。',
          },
        ],
      },
      'likeCount': 96,
      'favoriteCount': 13,
      'shareCount': 5,
    },
    {
      'id': 'circle_gentle_plain_body_only',
      'postId': 'circle_gentle_plain_body_only',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'authorId': 'u8',
      'authorNickname': '慢速纪要',
      'authorAvatarUrl':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
      'title': '',
      'body': '没有标题也没封面，只保留一段真正想被圈友读到的正文，作为最轻的一张文字卡。',
      'summary': '没有标题也没封面，只保留一段真正想被圈友读到的正文，作为最轻的一张文字卡。',
      'articleTemplate': 'gentle',
      'articleFontPreset': 'rounded',
      'articlePresentationVersion': 1,
      'circleIds': ['circle_photo_01', 'c2'],
      'circleNames': ['光影摄影社', '旅行手账'],
      'circleSummaries': [
        {'id': 'circle_photo_01', 'name': '光影摄影社'},
        {'id': 'c2', 'name': '旅行手账'},
      ],
      'circleName': '光影摄影社',
      'articleDocument': {
        'title': '',
        'body':
            '回家路上，我把路灯下那几句还没散掉的话先记下来。\n没有标题也没有封面，正文自己决定了这一页要从哪里开始。\n如果一段内容真的足够完整，它本身就能成为一张轻巧的圈子卡片。',
        'blocks': [
          {
            'id': 'circle_gentle_plain_body_only_p0',
            'type': 'paragraph',
            'text': '回家路上，我把路灯下那几句还没散掉的话先记下来。',
          },
          {
            'id': 'circle_gentle_plain_body_only_h2',
            'type': 'heading2',
            'text': '从正文起笔',
          },
          {
            'id': 'circle_gentle_plain_body_only_p1',
            'type': 'paragraph',
            'text': '没有标题也没有封面，正文自己决定了这一页要从哪里开始。',
          },
          {
            'id': 'circle_gentle_plain_body_only_section',
            'type': 'sectionTitle',
            'text': '收束',
          },
          {
            'id': 'circle_gentle_plain_body_only_p2',
            'type': 'paragraph',
            'text': '如果一段内容真的足够完整，它本身就能成为一张轻巧的圈子卡片。',
          },
        ],
      },
      'likeCount': 83,
      'favoriteCount': 11,
      'shareCount': 4,
    },
  ];

  static List<Map<String, dynamic>> get circleFeedItems => _circleFeedWireSeeds
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);

  static List<PostBaseDto>? _catalogCircleFeedPostDtosCache;

  /// 由 [_circleFeedWireSeeds] 尽力解析的帖子 DTO（与 Mock 仓库 [postBaseDtoFromMap] 行为一致）。
  static List<PostBaseDto> get catalogCircleFeedPostDtos {
    return _catalogCircleFeedPostDtosCache ??= () {
      final out = <PostBaseDto>[];
      for (final m in _circleFeedWireSeeds) {
        try {
          out.add(postBaseDtoFromMap(Map<String, dynamic>.from(m)));
        } catch (_) {}
      }
      return out;
    }();
  }

  static final CircleStatsWireDto catalogCircleStatsWire =
      CircleStatsWireDto.fromMap({
        'totalMembers': 128,
        'weeklyActive': 45,
        'totalPosts': 1024,
        'totalLikes': 128000,
      });

  static Map<String, dynamic> get stats =>
      Map<String, dynamic>.from(catalogCircleStatsWire.raw);
}
