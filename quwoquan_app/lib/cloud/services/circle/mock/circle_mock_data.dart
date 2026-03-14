/// 圈子域 Mock 数据（从 PrototypeMockData 搬迁）
class CircleMockData {
  const CircleMockData._();

  static Map<String, dynamic> get circleInfo => {
    'name': '光影摄影社',
    'id': 'circle_photo_01',
    'avatar':
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
    'cover':
        'https://images.unsplash.com/photo-1493125594441-2da1f5c644f5?q=80&w=1440',
    'desc': '汇聚全球摄影爱好者，分享快门背后的故事。无论你是专业摄影师还是手机摄影爱好者，这里都有你的位置。',
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

  static Map<String, Map<String, dynamic>> get categoryConfig => {
    'all': {
      'label': '推荐',
      'subCategories': ['综合', '热门', '新锐', '同城'],
      'desc': '智能聚合全站精彩内容',
    },
    'meet': {
      'label': '遇见',
      'subCategories': ['寻友', '婚恋', '同城', '树洞', '搭子'],
      'desc': '高效破冰，真实连接，遇见对的人',
    },
    'campus': {
      'label': '校园',
      'subCategories': ['母校', '院系', '年级', '校友会', '职场互助'],
      'desc': '连接校友关系，从学号到职场终身互助',
    },
    'car': {
      'label': '车友',
      'subCategories': ['品牌', '车型', '自驾', '改装', '同城车会'],
      'desc': '发现同款生活方式，开启座驾新旅程',
    },
    'humanity': {
      'label': '人文',
      'subCategories': ['艺术', '影像', '文学', '历史', '设计'],
      'desc': '探讨人类文明的极致美学',
    },
    'life': {
      'label': '生活',
      'subCategories': ['穿搭', '家居', '萌宠', '情感', '亲子'],
      'desc': '分享日常，发现生活中的小确幸',
    },
    'sports': {
      'label': '运动',
      'subCategories': ['健身', '户外', '球类', '养生', '竞技'],
      'desc': '挑战自我，享受流汗的快感',
    },
    'tech': {
      'label': '科技',
      'subCategories': ['数码', 'AI', '编程', '智能', '航天'],
      'desc': '追踪前沿趋势，探索未来可能',
    },
    'travel': {
      'label': '旅行',
      'subCategories': ['城市', '露营', '异域', '攻略', '徒步'],
      'desc': '看世界，见众生，在路上发现真我',
    },
    'food': {
      'label': '美食',
      'subCategories': ['探店', '烹饪', '茶酒', '咖啡', '烘焙'],
      'desc': '唯美食不可辜负，分享味蕾惊喜',
    },
  };

  static List<Map<String, dynamic>> get circles => [
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

  static List<Map<String, dynamic>> get members => [
    {
      'id': 'u1',
      'name': '陈一发',
      'avatar':
          'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
      'role': 'member',
      'joinedAt': '2024-01-15',
    },
    {
      'id': 'u2',
      'name': '周杰伦',
      'avatar':
          'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=100',
      'role': 'admin',
      'joinedAt': '2024-01-01',
    },
    {
      'id': 'u3',
      'name': '李青云',
      'avatar':
          'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
      'role': 'owner',
      'joinedAt': '2023-12-01',
    },
  ];

  static List<Map<String, dynamic>> get files => [
    {
      'id': 'f1',
      'name': '摄影指南.pdf',
      'fileType': 'file',
      'mimeType': 'application/pdf',
      'sizeBytes': 2097152,
      'uploaderId': 'u3',
      'status': 'active',
      'createdAt': '2024-02-01',
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
    },
  ];

  static List<Map<String, dynamic>> get circleFeedItems => [
    {
      'id': 'circle_post_moment_1',
      'circleId': 'circle_photo_01',
      'type': 'moment',
      'contentType': 'micro',
      'contentIdentity': 'moment',
      'coverUrl':
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=900',
      'imageUrls': [
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=900',
      ],
      'likeCount': 128,
    },
    {
      'id': 'circle_post_image_1',
      'circleId': 'circle_photo_01',
      'type': 'photo',
      'contentType': 'image',
      'contentIdentity': 'work',
      'coverUrl':
          'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=900',
      'imageUrls': [
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=900',
      ],
      'likeCount': 342,
    },
    {
      'id': 'circle_post_video_1',
      'circleId': 'circle_photo_01',
      'type': 'video',
      'contentType': 'video',
      'contentIdentity': 'work',
      'thumbnailUrl':
          'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=900',
      'likeCount': 211,
    },
    {
      'id': 'circle_post_note_1',
      'circleId': 'circle_photo_01',
      'type': 'article',
      'contentType': 'article',
      'contentIdentity': 'work',
      'coverUrl':
          'https://images.unsplash.com/photo-1455390582262-044cdead277a?w=900',
      'likeCount': 89,
    },
  ];

  static Map<String, dynamic> get stats => {
    'totalMembers': 128,
    'weeklyActive': 45,
    'totalPosts': 1024,
    'totalLikes': 128000,
  };
}
