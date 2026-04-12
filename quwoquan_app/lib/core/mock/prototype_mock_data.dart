// ignore_for_file: prefer_single_quotes
// Mock 数据 1:1 复制自 趣我圈2026/src 对应 TSX，不得删减字段或条数。
// 每段数据顶部注明来源文件。

import 'package:quwoquan_app/core/constants/app_concept_constants.dart';

/// 发现页 / 作者主页 / 圈子页等各页面 mock 数据，与原型 TSX 逐字段一致。
///
/// **弱类型策略**：历史 TSX 1:1 切片仍为 `Map<String, dynamic>`；**新增** mock 行在有 codegen DTO 时应优先 `Map<String, Object?>.from(dto.toMap())`（session_c §6）。
///
/// **与内容域 canonical 数据**：发现区 Feed wire 已以 [ContentMockData]（`discovery_*`）为单一真相；
/// [MockAppContentRepository.articleById] 已委托 [ContentMockData.articleWireByPostId]；本类仍保留 TSX 1:1
/// `discovery*` 切片供非内容域原型使用。
class PrototypeMockData {
  PrototypeMockData._();

  // ==================== DiscoveryFeed.tsx discoveryData (moment) ====================
  /// 1:1 来自 DiscoveryFeed.tsx activeType === 'moment' 的 return 数组（4 条）
  static List<Map<String, dynamic>> get discoveryMomentData {
    return [
      {
        'id': 'm4',
        'type': 'moment',
        'user': {
          'id': 'u4',
          'name': '李想',
          'avatar':
              'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100&h=100&fit=crop',
          'isVip': true,
          'badge': 'V',
          'isOfficial': true,
        },
        'timeAgo': '249.9万人关注了Ta',
        'content':
            '看他飞奔下车的样子，真帅！如果谁能联系上车主，能不能帮我转告一下，我可不可以去请他吃个饭？ //@理想汽车:点赞每一份挺身而出的勇气！',
        'quotedPost': {
          'user': '央视新闻',
          'content':
              '#浙FFJ3808救完人默默离开#【#男子急刹飞奔一把拉回轻生女子#】近日，浙江海盐，一女子欲跳桥轻生。',
          'media': [
            {
              'type': 'video',
              'url':
                  'https://images.unsplash.com/photo-1692735345453-bcb80bf6890d?w=800&h=450&fit=crop',
              'thumbnail':
                  'https://images.unsplash.com/photo-1692735345453-bcb80bf6890d?w=800&h=450&fit=crop',
              'duration': '00:24',
              'width': 800,
              'height': 450,
            },
          ],
        },
        'likes': 1581,
        'comments': 301,
        'shares': 112,
      },
      {
        'id': 'm1',
        'type': 'moment',
        'user': {
          'id': 'u1',
          'name': '你的皮炎有点辣',
          'avatar':
              'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100&h=100&fit=crop',
          'isVip': true,
          'badge': 'II',
        },
        'timeAgo': '昨天 10:56',
        'source': 'OPPO A5',
        'content': '左边是董宇辉的办公室，右边是俞敏洪的办公室，说明什么？',
        'media': [
          {
            'type': 'image',
            'url':
                'https://images.unsplash.com/photo-1566699270403-3f7e3f340664?w=600&h=600&fit=crop',
            'width': 600,
            'height': 600,
          },
          {
            'type': 'image',
            'url':
                'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=600&h=600&fit=crop',
            'width': 600,
            'height': 600,
          },
        ],
        'likes': 132,
        'comments': 36,
        'shares': 4,
        'isLiked': false,
      },
      {
        'id': 'm2',
        'type': 'moment',
        'user': {
          'id': 'u2',
          'name': '仅分组可见',
          'avatar':
              'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100&h=100&fit=crop',
          'isVip': true,
          'badge': 'II',
        },
        'timeAgo': '1-29',
        'source': '微博视频号',
        'content': '最害怕的事情还是发生了，船过去了船夫没赶上……',
        'media': [
          {
            'type': 'video',
            'url':
                'https://images.unsplash.com/photo-1736171545084-301185012571?w=450&h=800&fit=crop',
            'duration': '00:15',
            'thumbnail':
                'https://images.unsplash.com/photo-1736171545084-301185012571?w=450&h=800&fit=crop',
            'width': 450,
            'height': 800,
          },
        ],
        'likes': 452,
        'comments': 18,
        'shares': 37,
      },
      {
        'id': 'm3',
        'type': 'moment',
        'user': {
          'id': 'u3',
          'name': '原价帝吧',
          'avatar':
              'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100&h=100&fit=crop',
          'isVip': true,
          'badge': 'III',
        },
        'timeAgo': '382.6万人关注了Ta',
        'content':
            '只要我不尴尬，尴尬的就是别人——投资金银的侃爷Kanye West和妻子比安卡 Bianca Censori 出镜混剪📷 #金银V型反转##黄金#',
        'media': List.generate(9, (i) => <String, dynamic>{
          'type': 'image',
          'url':
              "https://images.unsplash.com/photo-1762343290960-74b50d205fb8?w=300&h=300&fit=crop&q=80&sig=$i",
          'width': 300,
          'height': 300,
        }),
        'likes': 1560,
        'comments': 420,
        'shares': 89,
      },
    ];
  }

  /// 1:1 来自 DiscoveryFeed.tsx activeType === 'photo' 的 return 数组（10 条，含 images 字段）
  /// aspectRatio: 宽/高，用于美图流自适应高度（最大 9:16）
  static List<Map<String, dynamic>> get discoveryPhotoData {
    return [
      {
        'id': 'd1',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1518152006812-edab29b069ac?w=800',
        'images': ['img1', 'img2'],
        'aspectRatio': 1.2,
        'author': {'id': 'nature_photographer', 'name': '自然摄影师', 'avatar': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100'},
      },
      {
        'id': 'd2',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800',
        'aspectRatio': 0.8,
        'author': {'id': 'travel_photographer', 'name': '旅行摄影师', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100'},
      },
      {
        'id': 'd4',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=800',
        'images': ['img1', 'img2', 'img3'],
        'aspectRatio': 1.0,
        'author': {'id': 'street_photo', 'name': '街头摄影', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100'},
      },
      {
        'id': 'd5',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800',
        'aspectRatio': 1.5,
        'author': {'id': 'nature_photographer', 'name': '自然摄影师', 'avatar': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100'},
      },
      {
        'id': 'd6',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=800',
        'author': {'id': 'travel_photographer', 'name': '旅行摄影师', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100'},
      },
      {
        'id': 'd10',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1500673922987-e212871fec22?w=800',
        'author': {'id': 'street_photo', 'name': '街头摄影', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100'},
      },
      {
        'id': 'd11',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1493863641943-9b68992a8d07?w=800',
        'author': {'id': 'nature_photographer', 'name': '自然摄影师', 'avatar': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100'},
      },
      {
        'id': 'd12',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1504198458649-3128b932f49e?w=800',
        'author': {'id': 'travel_photographer', 'name': '旅行摄影师', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100'},
      },
      {
        'id': 'd13',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
        'author': {'id': 'street_photo', 'name': '街头摄影', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100'},
      },
      {
        'id': 'd14',
        'type': 'image',
        'thumbnail': 'https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?w=800',
        'author': {'id': 'nature_photographer', 'name': '自然摄影师', 'avatar': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100'},
      },
    ];
  }

  /// 历史文章 mock（TSX 形状）；应用内文章详情 mock 请用 [ContentMockData.articleWireByPostId]。
  static Map<String, dynamic>? articleById(String id) {
    try {
      return discoveryArticleData.firstWhere((a) => a['id'] == id);
    } catch (_) {
      return null;
    }
  }

  /// 1:1 来自 DiscoveryFeed.tsx activeType === 'article' 的 return 数组（4 条，含 coverImage/images/displayStyle/layoutMode/theme/contentHtml）
  static List<Map<String, dynamic>> get discoveryArticleData {
    return [
      {
        'id': 'web-dev',
        'type': 'article',
        'category': '科技',
        'title': '2024年现代Web开发趋势：从服务端组件到边缘计算',
        'description':
            '探讨React Server Components如何改变前端架构，以及Edge Runtime带来的性能飞跃。',
        'coverImage': 'https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800',
        'images': ['https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800'],
        'displayStyle': 'left-right',
        'layoutMode': 'float-right',
        'theme': {'bg': '#ffffff', 'text': '#172554', 'fontFamily': 'sans-serif'},
        'contentHtml':
            '<p class="mb-6 text-lg leading-relaxed">随着Next.js 14的发布，React Server Components (RSC) 终于走入大众视野。</p>',
        'author': {
          'name': 'TechDaily',
          'avatar': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
          'isVip': true,
          'badge': 'V',
        },
        'date': '2小时前',
        'stats': {'likes': 1240, 'comments': 56, 'shares': 89},
      },
      {
        'id': 'calligraphy',
        'type': 'article',
        'category': '文化',
        'title': '墨韵流芳：汉字书法中的空间美学与精神寄托',
        'description': '在黑与白的交织中，感受传统文化的独特魅力。',
        'coverImage': 'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
        'images': [
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
          'https://images.unsplash.com/photo-1545996124-0501eb296251?w=800',
        ],
        'displayStyle': 'top-bottom-1',
        'layoutMode': 'hero',
        'theme': {'bg': '#fafafa', 'text': '#27272a', 'fontFamily': 'serif'},
        'contentHtml': '<p>书法，是中国传统文化中最抽象也最具体的艺术形式。</p>',
        'author': {
          'name': '墨韵',
          'avatar': 'https://images.unsplash.com/photo-1545996124-0501eb296251?w=100',
          'isOfficial': true,
        },
        'date': '昨天',
        'stats': {'likes': 892, 'comments': 34, 'shares': 12},
      },
      {
        'id': 'pasta',
        'type': 'article',
        'category': '美食',
        'title': '意式风情：三种经典酱汁的制作秘籍',
        'description': '从博洛尼亚肉酱到罗勒青酱，带你领略正宗意大利风味。',
        'coverImage': 'https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800',
        'images': ['https://images.unsplash.com/photo-1498579150354-977475b7ea0b?w=800'],
        'displayStyle': 'top-bottom-3',
        'layoutMode': 'carousel',
        'theme': {'bg': '#fff7ed', 'text': '#431407', 'fontFamily': 'sans-serif'},
        'contentHtml': '<p>意大利面的灵魂在于酱汁。</p>',
        'author': {
          'name': 'Chef Mario',
          'avatar': 'https://images.unsplash.com/photo-1583394293214-28ded15ee548?w=100',
          'isVip': true,
          'badge': 'II',
        },
        'date': '3天前',
        'stats': {'likes': 2105, 'comments': 142, 'shares': 304},
      },
      {
        'id': 'art_1',
        'type': 'article',
        'category': '设计',
        'title': 'UI设计的心理学原理：色彩、布局与用户认知',
        'description': '为什么某些配色能让人产生购买欲？深入解析设计背后的心理学机制。',
        'coverImage': 'https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800',
        'images': ['https://images.unsplash.com/photo-1561070791-2526d30994b5?w=800'],
        'displayStyle': 'left-right',
        'layoutMode': 'split',
        'theme': {'bg': '#ffffff', 'text': '#1f2937', 'fontFamily': 'sans-serif'},
        'contentHtml': '<p>设计不仅仅是视觉的艺术，更是心理的博弈。</p>',
        'author': {
          'name': 'DesignGuru',
          'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
          'isVip': true,
        },
        'date': '5小时前',
        'stats': {'likes': 3200, 'comments': 120, 'shares': 450},
      },
    ];
  }

  // ==================== VideoImmersionView.tsx mockVideos ====================
  /// 1:1 来自 VideoImmersionView.tsx mockVideos（3 条）
  static List<Map<String, dynamic>> get discoveryVideoData {
    return [
      {
        'id': 'v1',
        'thumbnail': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=800',
        'author': {'name': '楹语小筑', 'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100', 'id': 'a1'},
        'content': '东京凌晨两点的街道，有一种难以言喻的孤独美。#治愈系 #东京之夜 #氛围感',
        'likes': '12.5k',
        'comments': '892',
        'shares': '1.2k',
        'musicName': 'Tokyo Midnight Lofi',
        'duration': 45,
      },
      {
        'id': 'v2',
        'thumbnail': 'https://images.unsplash.com/photo-1492691527719-9d1e07e534b4?w=800',
        'author': {'name': '自然摄影师', 'avatar': 'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=100', 'id': 'a2'},
        'content': '在大自然中找回内心的平静。🌲✨ #森林漫步 #自然景观 #心灵治愈',
        'likes': '8.2k',
        'comments': '430',
        'shares': '560',
        'musicName': 'Forest Whispers',
        'duration': 15,
      },
      {
        'id': 'v3',
        'thumbnail': 'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=800',
        'author': {'name': '未来科技', 'avatar': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=100', 'id': 'a3'},
        'content': '2026年，我们的生活将如何被AI改变？一分钟带你了解。#科技趋势 #未来已来',
        'likes': '45k',
        'comments': '3.4k',
        'shares': '12k',
        'musicName': 'Digital Future Beats',
        'duration': 59,
      },
    ];
  }

  // ==================== AuthorProfile.tsx works / lifeItems / commonAvatars ====================
  /// 1:1 来自 AuthorProfile.tsx const works（6 条）
  static List<Map<String, dynamic>> get authorProfileWorks {
    return [
      {
        'id': 'w1',
        'type': 'photo',
        'title': '光影的节奏',
        'image': 'https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400',
        'likes': '1.2k',
        'date': '2025-12-20',
        'desc': '在布鲁塞尔的午后，捕捉到的一组极简主义建筑光影。',
      },
      {
        'id': 'w2',
        'type': 'video',
        'title': '森林的呼吸',
        'image': 'https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400',
        'likes': '840',
        'date': '2025-12-15',
        'desc': '4K延时摄影，记录大兴安岭清晨云雾缭绕的过程。',
      },
      {
        'id': 'w3',
        'type': 'article',
        'title': '极简摄影的真谛',
        'image': 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400',
        'likes': '2.1k',
        'date': '2025-12-10',
        'desc': '通过剥离不必要的元素，我们才能看见事物的本质。',
      },
      {
        'id': 'w4',
        'type': 'photo',
        'title': '咖啡厅一角',
        'image': 'https://images.unsplash.com/photo-1650211573412-9d36d0cbbf00?q=80&w=400',
        'likes': '560',
        'date': '2025-12-05',
        'desc': '深夜的咖啡馆，除了香味，还有孤独。',
      },
      {
        'id': 'w5',
        'type': 'photo',
        'title': '科技与生活',
        'image': 'https://images.unsplash.com/photo-1731160807880-daf859b64420?q=80&w=400',
        'likes': '1.5k',
        'date': '2025-11-28',
        'desc': '当机械键盘遇上温暖的灯光，是程序员的浪漫。',
      },
      {
        'id': 'w6',
        'type': 'video',
        'title': '高山之巅',
        'image': 'https://images.unsplash.com/photo-1766852254215-ec02eeec50fa?q=80&w=400',
        'likes': '920',
        'date': '2025-11-20',
        'desc': '无人机视角下的雪山，感受大自然的伟力。',
      },
    ];
  }

  /// 1:1 来自 AuthorProfile.tsx const lifeItems（4 条）
  static List<Map<String, dynamic>> get authorProfileLifeItems {
    return [
      {
        'id': 'i1',
        'name': '阿那亚礼堂',
        'category': '足迹',
        'categoryKey': 'footprint',
        'image': 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400',
        'isMutual': true,
        'desc': '在海边的孤独感中寻找创作灵感。',
      },
      {
        'id': 'i2',
        'name': '《摄影的哲学》',
        'category': '书影音',
        'categoryKey': 'soul',
        'image': 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?q=80&w=400',
        'isMutual': true,
        'desc': '比起技巧，我更痴迷于思考快门背后。',
      },
      {
        'id': 'i3',
        'name': 'Dirty Coffee',
        'category': '味蕾',
        'categoryKey': 'taste',
        'image': 'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?q=80&w=400',
        'isMutual': true,
        'desc': '喜欢那种冷热交替的冲突感。',
      },
      {
        'id': 'i4',
        'name': 'Leica M11',
        'category': '爱物',
        'categoryKey': 'private',
        'image': 'https://images.unsplash.com/photo-1648049003029-3b3b32cb9a1f?q=80&w=400',
        'isMutual': true,
        'desc': '它是我身体的延伸。',
      },
    ];
  }

  /// 1:1 来自 AuthorProfile.tsx const commonAvatars（3 条）
  static List<String> get authorProfileCommonAvatars {
    return [
      'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
      'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=100',
      'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
    ];
  }

  // ==================== CirclePageV2.tsx circleInfo ====================
  /// 1:1 来自 CirclePageV2.tsx const circleInfo
  static Map<String, dynamic> get circlePageCircleInfo {
    return {
      'name': '光影摄影社',
      'id': 'circle_photo_01',
      'avatar': 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
      'cover': 'https://images.unsplash.com/photo-1493125594441-2da1f5c644f5?q=80&w=1440',
      'desc':
          '汇聚全球摄影爱好者，分享快门背后的故事。无论你是专业摄影师还是手机摄影爱好者，这里都有你的位置。',
      'stats': {
        'members': '128',
        'groups': '26',
        'fans': '45.2k',
        'likes': '128k',
      },
      'hasNewMessages': true,
    };
  }

  // ==================== circles/mockData.ts CATEGORY_CONFIG ====================
  /// 1:1 来自 circles/mockData.ts CATEGORY_CONFIG（兴趣维度 + 子分类）
  static Map<String, Map<String, dynamic>> get circlesCategoryConfig {
    return {
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
  }

  /// 帮读摘要：一句话综述 + 分维度展开事实。oneLiner 为单句概括；dimensions 为维度列表，每项含 dimensionKey、title、items（事实条，含 actorName、titleOrDescription、likes、workId、workIds 等）。
  static Map<String, dynamic> get helperReadSummary {
    return {
      'oneLiner':
          '自上次阅读以来，3 位趣友发布了新作，2 个圈子有 5 条新动态，你的趣友在互动 2 个新圈子。',
      'dimensions': [
        {
          'dimensionKey': 'friendPublish',
          'title': '趣友新动态',
          'items': [
            {
              'actorName': '李想',
              'titleOrDescription': '发布了一条微趣',
              'likes': 1581,
              'workId': 'm4',
              'workType': 'moment',
            },
            {
              'actorName': '你的皮炎有点辣',
              'titleOrDescription': '发布了一条微趣',
              'likes': 234,
              'workId': 'm1',
              'workType': 'moment',
            },
            {
              'actorName': '墨韵',
              'titleOrDescription': '发布了文章《墨韵流芳：汉字书法中的空间美学与精神寄托》',
              'likes': 892,
              'workId': 'calligraphy',
              'workType': 'article',
            },
          ],
        },
        {
          'dimensionKey': 'newFollowPublish',
          'title': '刚加入的趣友',
          'items': [
            {
              'actorName': 'TechDaily',
              'titleOrDescription': '新关注的 1 位趣友发布了文章《2024年现代Web开发趋势》',
              'likes': 1240,
              'workId': 'web-dev',
              'workType': 'article',
            },
          ],
        },
        {
          'dimensionKey': 'circleMoment',
          'title': '圈子发生了什么',
          'items': [
            {
              'actorName': '徕卡影像志',
              'titleOrDescription': '圈内有 3 条新微趣',
              'likes': 56,
              'workIds': ['m4', 'm1'],
              'circleId': 'c-human-1',
            },
            {
              'actorName': '我的摄影圈 (圈主)',
              'titleOrDescription': '圈内有 2 条新动态',
              'likes': 12,
              'workIds': ['m1'],
              'circleId': 'c-photo-owner',
            },
          ],
        },
        {
          'dimensionKey': 'interactionWithYou',
          'title': '谁与你互动',
          'items': [
            {
              'actorName': '李想',
              'titleOrDescription': '赞了你的微趣',
              'workId': 'm1',
              'workType': 'moment',
            },
            {
              'actorName': '3 位趣友',
              'titleOrDescription': '共同点赞了《意式风情：三种经典酱汁的制作秘籍》',
              'likes': 2105,
              'workId': 'pasta',
              'workType': 'article',
            },
          ],
        },
        {
          'dimensionKey': 'explore',
          'title': '探索推荐',
          'items': [
            {
              'actorName': '2 个圈子',
              'titleOrDescription': '你的趣友在互动：互联网校友内推圈、静安·安福路下午茶搭子',
              'circleIds': ['c-cam-2', 'c-meet-1'],
            },
            {
              'actorName': '与你兴趣相近',
              'titleOrDescription': '科技前沿 (管理员)、极氪001·全国自驾团',
              'circleIds': ['c-tech-admin', 'c-car-2'],
            },
          ],
        },
      ],
    };
  }

  /// 1:1 来自 circles/mockData.ts MOCK_CIRCLES
  static List<Map<String, dynamic>> get circlesMockCircles {
    return [
      {
        'id': 'c-cam-1',
        'name': '上海交大·2020级校友',
        'avatar': 'https://images.unsplash.com/photo-1541339907198-e08756ebafe1?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1000&fit=crop',
        'memberCount': 2800,
        'description': 'SJTU Class of 2020 alumni network.',
        'type': 'class',
        'categoryId': 'campus',
        'school': '上海交通大学',
      },
      {
        'id': 'c-cam-2',
        'name': '互联网校友内推圈',
        'avatar': 'https://images.unsplash.com/photo-1521737711867-e3b97375f902?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=1000&fit=crop',
        'memberCount': 15600,
        'description': '大厂校友互助，内推直达。',
        'type': 'official',
        'categoryId': 'campus',
        'subCategory': '职场互助',
      },
      {
        'id': 'c-car-1',
        'name': 'Model 3 焕新版·上海车友会',
        'avatar': 'https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1536700503339-1e4b06520771?w=1000&fit=crop',
        'memberCount': 4500,
        'description': '特斯拉Model 3车主深度交流、自驾活动。',
        'type': 'fan_club',
        'categoryId': 'car',
        'carBrand': '特斯拉',
      },
      {
        'id': 'c-car-2',
        'name': '极氪001·全国自驾团',
        'avatar': 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1469033011854-3a045667b738?w=1000&fit=crop',
        'memberCount': 8900,
        'description': '开启极氪式生活，发现最美自驾路线。',
        'type': 'tour',
        'categoryId': 'car',
        'carBrand': '极氪',
      },
      {
        'id': 'c-meet-1',
        'name': '静安·安福路下午茶搭子',
        'avatar': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1501339817302-ee4b91357e6a?w=1000&fit=crop',
        'memberCount': 12500,
        'description': '附近的人，此刻正有空，一起喝咖啡？',
        'type': 'encounter',
        'categoryId': 'meet',
        'location': '上海安福路',
      },
      {
        'id': 'c-meet-2',
        'name': '95后互联网互助树洞',
        'avatar': 'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=1000&fit=crop',
        'memberCount': 18900,
        'description': '成年人的世界，总需要一个宣泄口。',
        'type': 'encounter',
        'categoryId': 'meet',
        'subCategory': '树洞',
      },
      {
        'id': 'c-human-1',
        'name': '徕卡影像志',
        'avatar': 'https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1495121553079-4c61bbbc19df?w=1000&fit=crop',
        'memberCount': 28000,
        'description': '用镜头记录世界，传递有温度的内容。',
        'type': 'interest',
        'categoryId': 'humanity',
        'subCategory': '影像',
        'role': 'admin',
      },
      {
        'id': 'c-photo-owner',
        'name': '我的摄影圈 (圈主)',
        'avatar': 'https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1554080353-a576cf803bda?w=1000&fit=crop',
        'memberCount': 128,
        'description': '这是一个测试圈主权限的圈子。',
        'type': 'interest',
        'categoryId': 'humanity',
        'subCategory': '摄影',
        'role': 'owner',
      },
      {
        'id': 'c-tech-admin',
        'name': '科技前沿 (管理员)',
        'avatar': 'https://images.unsplash.com/photo-1518770660439-4636190af475?w=200&h=200&fit=crop',
        'cover': 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1000&fit=crop',
        'memberCount': 560,
        'description': '这是一个测试管理员权限的圈子。',
        'type': 'interest',
        'categoryId': 'tech',
        'role': 'admin',
      },
    ];
  }

  // ==================== messages/MockMessageData.ts MOCK_CONVERSATIONS + 私人助理 ====================
  /// 私人助理头像 URL（对话列表与气泡中均使用此头像）
  static const String chatAssistantAvatarUrl =
      'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=400';

  /// 私人助理会话（用于趣聊 Tab 全部，标题等展示名来自 AppConceptConstants）
  static Map<String, dynamic> get chatAssistantConversation {
    return {
      'id': AppConceptConstants.assistantConversationId,
      'title': AppConceptConstants.assistantDisplayTitle,
      'avatar': chatAssistantAvatarUrl,
      'lastMessage': '主人早安，昨天你关注的"复古胶片圈"有5条热门更新...',
      'lastMessageTime': '刚刚',
      'unreadCount': 0,
      'type': 'private',
      'isSpecial': true,
    };
  }

  /// 1:1 来自 MockMessageData.ts MOCK_CONVERSATIONS（全部 + @我/未读/密信 筛选用）
  static List<Map<String, dynamic>> get chatMockConversations {
    return [
      {
        'id': 'conv_private_zhao',
        'type': 'private',
        'title': '用户A',
        'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400',
        'lastMessage': '周末一起去拍照吗？',
        'lastMessageTime': '10分钟前',
        'unreadCount': 2,
        'hasMention': false,
      },
      {
        'id': 'conv_private_wang',
        'type': 'private',
        'title': '用户B',
        'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400',
        'lastMessage': '谢谢分享，学到很多！',
        'lastMessageTime': '1小时前',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_li',
        'type': 'private',
        'title': '用户C',
        'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400',
        'lastMessage': '[图片]',
        'lastMessageTime': '3小时前',
        'unreadCount': 1,
        'hasMention': false,
      },
      {
        'id': 'conv_group_photo',
        'type': 'group',
        'title': '摄影交流群',
        'avatar': 'https://images.unsplash.com/photo-1452457807411-4979b707c5be?w=400',
        'lastMessage': '用户D: 这张照片构图很棒！',
        'lastMessageTime': '30分钟前',
        'unreadCount': 5,
        'hasMention': false,
      },
      {
        'id': 'conv_circle_1',
        'type': 'circle',
        'title': '摄影班交流',
        'avatar': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400',
        'lastMessage': '🔥 推荐秘境 💬 欢迎加入社群😘',
        'lastMessageTime': '2025年12月19日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_1',
        'type': 'private',
        'title': '用户D',
        'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400',
        'lastMessage': '[链接] https://m.tb.cn/h.7WmACZJ?tk=...',
        'lastMessageTime': '2025年12月18日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_2',
        'type': 'private',
        'title': '用户E',
        'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400',
        'lastMessage': '👍',
        'lastMessageTime': '2025年12月17日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_circle_2',
        'type': 'circle',
        'title': '20251217坂田合同商务...',
        'avatar': 'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=400',
        'lastMessage': '林土 周东淼 已解读该消息',
        'lastMessageTime': '2025年12月17日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_3',
        'type': 'private',
        'title': '用户F',
        'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400',
        'lastMessage': '[图片]',
        'lastMessageTime': '2025年12月17日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_4',
        'type': 'private',
        'title': '迷邮助手-楚辉',
        'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400',
        'lastMessage': '[条目] [AI星图] 💄 @迪海晴龙 今晚修了一个的好好',
        'lastMessageTime': '2025年12月11日',
        'unreadCount': 0,
        'hasMention': true,
      },
      {
        'id': 'conv_circle_3',
        'type': 'circle',
        'title': '爪爪猫球-组半电商，有...',
        'avatar': 'https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400',
        'lastMessage': '[图片] 重一致反而配也来一趟你🦘 需要',
        'lastMessageTime': '2025年12月8日',
        'unreadCount': 0,
        'hasMention': false,
      },
      {
        'id': 'conv_private_5',
        'type': 'private',
        'title': 'AAA孙磊-组半电商，有...',
        'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400',
        'lastMessage': '好一家强反而配也🤝 蹿动',
        'lastMessageTime': '2025年11月30日',
        'unreadCount': 0,
        'hasMention': false,
      },
    ];
  }

  /// 密信 Tab 专用：type == encrypted 的会话（需解锁后展示）
  static List<Map<String, dynamic>> get chatEncryptedConversations {
    return [
      {
        'id': 'conv_encrypted_1',
        'type': 'encrypted',
        'title': '私密项目组',
        'avatar': 'https://images.unsplash.com/photo-1614028674026-a65e31bfd27c?w=400',
        'lastMessage': '[加密消息] 查看需要验证身份',
        'lastMessageTime': '2025年12月22日',
        'unreadCount': 1,
        'isEncrypted': true,
        'requiresAuth': true,
      },
      {
        'id': 'conv_encrypted_2',
        'type': 'encrypted',
        'title': '与 神秘人 的密信',
        'avatar': 'https://images.unsplash.com/photo-1566492031773-4f4e44671857?w=400',
        'lastMessage': '[加密消息] 文件已发送',
        'lastMessageTime': '昨天',
        'unreadCount': 0,
        'isEncrypted': true,
        'requiresAuth': true,
      },
    ];
  }

  /// @我 Tab：含有提及当前用户的会话（hasMention == true）
  static List<Map<String, dynamic>> get chatMockConversationsAtMe {
    return chatMockConversations.where((c) => c['hasMention'] == true).toList();
  }

  /// 同好 Tab - 联系人（含趣聊中的会话对象，至少两屏；1:1 MockMessageData MOCK_CONTACTS 扩展）
  static List<Map<String, dynamic>> get chatMockContacts {
    return [
      // 星标 + 与趣聊会话对应
      {'id': 'user_123', 'displayName': '李摄影', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '风光摄影爱好者', 'isFriend': true, 'isStarred': true, 'metFrom': '风光摄影圈、人像摄影圈', 'lastInteraction': '发消息', 'lastInteractionTime': '1小时前'},
      {'id': 'user_111', 'displayName': '赵摄影师', 'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400', 'bio': '商业摄影师', 'isFriend': true, 'isStarred': true, 'metFrom': '人像摄影圈、摄影器材圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '3天前'},
      // 趣聊中的用户 A/B/C/D/E/F、迷邮助手、孙磊等
      {'id': 'user_a', 'displayName': '用户A', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '摄影交流圈', 'isFriend': true, 'isStarred': false, 'metFrom': '摄影交流圈', 'lastInteraction': '发消息', 'lastInteractionTime': '10分钟前'},
      {'id': 'user_b', 'displayName': '用户B', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '风光摄影圈', 'isFriend': true, 'isStarred': false, 'metFrom': '风光摄影圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '1小时前'},
      {'id': 'user_c', 'displayName': '用户C', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '人像摄影圈', 'isFriend': false, 'isStarred': false, 'metFrom': '人像摄影圈', 'lastInteraction': '点赞', 'lastInteractionTime': '3小时前'},
      {'id': 'user_d', 'displayName': '用户D', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '摄影交流圈', 'isFriend': true, 'isStarred': false, 'metFrom': '摄影交流圈', 'lastInteraction': '发链接', 'lastInteractionTime': '12月18日'},
      {'id': 'user_e', 'displayName': '用户E', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '风光摄影圈', 'isFriend': true, 'isStarred': false, 'metFrom': '风光摄影圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '12月17日'},
      {'id': 'user_f', 'displayName': '用户F', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '人像摄影圈', 'isFriend': true, 'isStarred': false, 'metFrom': '人像摄影圈', 'lastInteraction': '发图片', 'lastInteractionTime': '12月17日'},
      {'id': 'user_456', 'displayName': '王小明', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '人像摄影师', 'isFriend': true, 'isStarred': false, 'metFrom': '人像摄影圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '昨天'},
      {'id': 'user_789', 'displayName': '张三', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400', 'bio': '游戏爱好者', 'isFriend': false, 'isStarred': false, 'metFrom': '游戏交流圈', 'lastInteraction': '关注了你', 'lastInteractionTime': '昨天'},
      {'id': 'user_222', 'displayName': '书友小芳', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '科幻文学爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '科幻文学圈', 'lastInteraction': '发消息', 'lastInteractionTime': '4天前'},
      {'id': 'user_chuhui', 'displayName': '迷邮助手-楚辉', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400', 'bio': '技术交流圈', 'isFriend': true, 'isStarred': false, 'metFrom': '技术交流圈', 'lastInteraction': '发条目', 'lastInteractionTime': '12月11日'},
      {'id': 'user_sunlei', 'displayName': 'AAA孙磊-组半电商', 'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400', 'bio': '商务合作圈', 'isFriend': true, 'isStarred': false, 'metFrom': '商务合作圈', 'lastInteraction': '发消息', 'lastInteractionTime': '11月30日'},
      // 补充至两屏以上，多首字母
      {'id': 'user_a1', 'displayName': '安琪', 'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400', 'bio': '生活记录', 'isFriend': true, 'isStarred': false, 'metFrom': '生活圈', 'lastInteraction': '点赞', 'lastInteractionTime': '5天前'},
      {'id': 'user_b1', 'displayName': '毕涛', 'avatar': 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400', 'bio': '户外徒步', 'isFriend': false, 'isStarred': false, 'metFrom': '户外圈', 'lastInteraction': '关注', 'lastInteractionTime': '1周前'},
      {'id': 'user_c1', 'displayName': '陈默', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '读书会', 'isFriend': true, 'isStarred': false, 'metFrom': '读书圈', 'lastInteraction': '发消息', 'lastInteractionTime': '2天前'},
      {'id': 'user_f1', 'displayName': '方悦', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '插画师', 'isFriend': true, 'isStarred': false, 'metFrom': '艺术圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '3天前'},
      {'id': 'user_g1', 'displayName': '顾晨', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '数码爱好者', 'isFriend': false, 'isStarred': false, 'metFrom': '数码圈', 'lastInteraction': '评论', 'lastInteractionTime': '6天前'},
      {'id': 'user_h1', 'displayName': '黄小蕾', 'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400', 'bio': '美食探店', 'isFriend': true, 'isStarred': false, 'metFrom': '美食圈', 'lastInteraction': '发消息', 'lastInteractionTime': '1天前'},
      {'id': 'user_j1', 'displayName': '蒋明', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400', 'bio': '骑行爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '运动圈', 'lastInteraction': '点赞', 'lastInteractionTime': '4天前'},
      {'id': 'user_k1', 'displayName': '孔亮', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '电影爱好者', 'isFriend': false, 'isStarred': false, 'metFrom': '影评圈', 'lastInteraction': '关注', 'lastInteractionTime': '1周前'},
      {'id': 'user_l1', 'displayName': '刘洋', 'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400', 'bio': '旅行摄影', 'isFriend': true, 'isStarred': false, 'metFrom': '旅行圈', 'lastInteraction': '发消息', 'lastInteractionTime': '昨天'},
      {'id': 'user_m1', 'displayName': '马晓东', 'avatar': 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400', 'bio': '篮球爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '运动圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '5天前'},
      {'id': 'user_p1', 'displayName': '潘雨', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '手账达人', 'isFriend': true, 'isStarred': false, 'metFrom': '手账圈', 'lastInteraction': '评论', 'lastInteractionTime': '3天前'},
      {'id': 'user_q1', 'displayName': '钱多多', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '理财分享', 'isFriend': false, 'isStarred': false, 'metFrom': '财经圈', 'lastInteraction': '关注', 'lastInteractionTime': '2周前'},
      {'id': 'user_r1', 'displayName': '任晓雯', 'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400', 'bio': '写作爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '写作圈', 'lastInteraction': '发消息', 'lastInteractionTime': '2天前'},
      {'id': 'user_s1', 'displayName': '孙浩然', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400', 'bio': '吉他手', 'isFriend': true, 'isStarred': false, 'metFrom': '音乐圈', 'lastInteraction': '点赞', 'lastInteractionTime': '4天前'},
      {'id': 'user_t1', 'displayName': '唐果', 'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400', 'bio': '烘焙爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '美食圈', 'lastInteraction': '互相点赞', 'lastInteractionTime': '6天前'},
      {'id': 'user_w1', 'displayName': '吴磊', 'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'bio': '游戏主播', 'isFriend': false, 'isStarred': false, 'metFrom': '游戏圈', 'lastInteraction': '关注', 'lastInteractionTime': '1周前'},
      {'id': 'user_x1', 'displayName': '许静', 'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'bio': '瑜伽教练', 'isFriend': true, 'isStarred': false, 'metFrom': '健身圈', 'lastInteraction': '发消息', 'lastInteractionTime': '1天前'},
      {'id': 'user_y1', 'displayName': '杨帆', 'avatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'bio': '航拍爱好者', 'isFriend': true, 'isStarred': false, 'metFrom': '摄影圈', 'lastInteraction': '点赞', 'lastInteractionTime': '3天前'},
      {'id': 'user_z1', 'displayName': '周杰', 'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400', 'bio': '街舞老师', 'isFriend': true, 'isStarred': false, 'metFrom': '舞蹈圈', 'lastInteraction': '评论', 'lastInteractionTime': '5天前'},
      {'id': 'user_z2', 'displayName': '郑小希', 'avatar': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400', 'bio': '宠物博主', 'isFriend': true, 'isStarred': false, 'metFrom': '宠物圈', 'lastInteraction': '发消息', 'lastInteractionTime': '昨天'},
    ];
  }

  /// 同好 - 圈子列表（简化）
  static List<Map<String, dynamic>> get chatMockContactCircles {
    return [
      {'id': 'circle_1', 'name': '风光摄影圈', 'avatar': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400', 'memberCount': '1.2k'},
      {'id': 'circle_2', 'name': '人像摄影圈', 'avatar': 'https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=400', 'memberCount': '890'},
    ];
  }

  /// 同好 - 群聊列表（与对话中的 group 对应）
  static List<Map<String, dynamic>> get chatMockContactGroups {
    return [
      {'id': 'conv_group_photo', 'name': '摄影交流群', 'avatar': 'https://images.unsplash.com/photo-1452457807411-4979b707c5be?w=400', 'memberCount': '128'},
    ];
  }

  /// 1:1 来自 circles/mockData.ts MOCK_ACTIVITIES
  static List<Map<String, dynamic>> get circlesMockActivities {
    return [
      {
        'id': 'a1',
        'type': 'live',
        'title': '静安寺附近校友连麦：今晚聊聊职场内推',
        'status': 'active',
        'circleId': 'c-cam-2',
        'circleName': '互联网校友内推圈',
        'participants': 1250,
        'image': 'https://images.unsplash.com/photo-1516280440614-37939bbacd81?w=800&fit=crop',
      },
      {
        'id': 'a2',
        'type': 'gathering',
        'title': '【车友招募】周末莫干山自驾游',
        'status': 'upcoming',
        'circleId': 'c-car-1',
        'circleName': 'Model 3 焕新版·上海车友会',
        'participants': 45,
        'image': 'https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?w=800&fit=crop',
      },
    ];
  }

  // ==================== 私人助理主页 memoryData / tasksData / skillsData ====================
  static List<Map<String, dynamic>> get assistantMemoryData {
    return [
      {'id': 1, 'type': 'post', 'title': '关于极简摄影的思考', 'date': '今天 10:24', 'icon': '📷'},
      {'id': 2, 'type': 'chat', 'title': '与"影者"讨论构图技巧', 'date': '昨天 15:30', 'icon': '💬'},
      {'id': 3, 'type': 'discovery', 'title': '收藏了"4:5美学"圈子的文章', 'date': '2月2日', 'icon': '🔖'},
    ];
  }

  static List<Map<String, dynamic>> get assistantTasksData {
    return [
      {'id': 1, 'title': '完成《城市节奏》摄影集', 'time': '14:00', 'status': 'pending', 'category': '计划'},
      {'id': 2, 'title': '回复圈子里的讨论', 'time': '16:30', 'status': 'completed', 'category': '待办'},
      {'id': 3, 'title': '晚间灵感整理', 'time': '21:00', 'status': 'pending', 'category': '待办'},
    ];
  }

  static List<Map<String, dynamic>> get assistantSkillsData {
    return [
      {'id': 'summary', 'name': '总结', 'desc': '每日/每周创作与社交汇总', 'active': true},
      {'id': 'travel', 'name': '旅行', 'desc': '出行攻略与目的地推荐', 'active': true},
      {'id': 'reminder', 'name': '提醒', 'desc': '关键信息与节日纪念日', 'active': false},
      {'id': 'organize', 'name': '整理', 'desc': '自动清理冗余信息与照片', 'active': false},
    ];
  }

  // ==================== MockMessageData.ts MOCK_CHAT_MESSAGES + 私人助理初始消息 ====================
  /// 按会话 ID 返回消息列表；助理会话使用 AppConceptConstants.assistantConversationId / assistantSenderId
  static List<Map<String, dynamic>> chatMessagesFor(String conversationId) {
    if (conversationId == AppConceptConstants.assistantConversationId) {
      final title = AppConceptConstants.assistantDisplayTitle;
      final avatar = chatAssistantAvatarUrl;
      return [
        {
          'id': 'a1',
          'conversationId': AppConceptConstants.assistantConversationId,
          'type': 'text',
          'content': '主人早安！我是你的$title。今天为你整理了待办事项和一些新发现。',
          'senderId': AppConceptConstants.assistantSenderId,
          'senderName': title,
          'senderAvatar': avatar,
          'timestamp': '09:00',
          'isRead': true,
          'isSelf': false,
        },
        {
          'id': 'a2',
          'conversationId': AppConceptConstants.assistantConversationId,
          'type': 'task_card',
          'content': '今日待办',
          'senderId': AppConceptConstants.assistantSenderId,
          'senderName': title,
          'senderAvatar': avatar,
          'timestamp': '09:00',
          'isRead': true,
          'isSelf': false,
          'tasks': [
            {'id': '1', 'title': '完成《城市节奏》摄影集', 'time': '14:00', 'status': 'pending'},
            {'id': '2', 'title': '回复圈子里的讨论', 'time': '16:30', 'status': 'completed'},
            {'id': '3', 'title': '晚间灵感整理', 'time': '21:00', 'status': 'pending'},
          ],
        },
      ];
    }
    final all = _chatMessagesMap[conversationId];
    if (all != null) return List<Map<String, dynamic>>.from(all);
    return [];
  }

  static final Map<String, List<Map<String, dynamic>>> _chatMessagesMap = {
    'conv_private_zhao': [
      {'id': 'msg_zhao_1', 'conversationId': 'conv_private_zhao', 'type': 'text', 'content': '你好，周末有空吗？', 'senderId': 'user_a', 'senderName': '用户A', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '今天 上午10:30', 'isRead': true, 'isSelf': false},
      {'id': 'msg_zhao_2', 'conversationId': 'conv_private_zhao', 'type': 'text', 'content': '有空啊，怎么了？', 'senderId': 'current_user', 'senderName': '我', 'senderAvatar': 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400', 'timestamp': '今天 上午10:32', 'isRead': true, 'isSelf': true},
      {'id': 'msg_zhao_3', 'conversationId': 'conv_private_zhao', 'type': 'text', 'content': '周末一起去拍照吗？', 'senderId': 'user_a', 'senderName': '用户A', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '今天 上午10:35', 'isRead': false, 'isSelf': false},
      {'id': 'msg_zhao_4', 'conversationId': 'conv_private_zhao', 'type': 'text', 'content': '听说那边的风景很不错', 'senderId': 'user_a', 'senderName': '用户A', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '今天 上午10:35', 'isRead': false, 'isSelf': false},
    ],
    'conv_private_wang': [
      {'id': 'msg_wang_1', 'conversationId': 'conv_private_wang', 'type': 'text', 'content': '你上次分享的那个摄影技巧太有用了！', 'senderId': 'user_b', 'senderName': '用户B', 'senderAvatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'timestamp': '昨天 下午3:20', 'isRead': true, 'isSelf': false},
      {'id': 'msg_wang_2', 'conversationId': 'conv_private_wang', 'type': 'text', 'content': '哈哈，有帮助就好', 'senderId': 'current_user', 'senderName': '我', 'senderAvatar': 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400', 'timestamp': '昨天 下午3:25', 'isRead': true, 'isSelf': true},
      {'id': 'msg_wang_3', 'conversationId': 'conv_private_wang', 'type': 'text', 'content': '我今天试了一下，效果很好', 'senderId': 'user_b', 'senderName': '用户B', 'senderAvatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'timestamp': '昨天 下午3:30', 'isRead': true, 'isSelf': false},
      {'id': 'msg_wang_4', 'conversationId': 'conv_private_wang', 'type': 'text', 'content': '谢谢分享，学到很多！', 'senderId': 'user_b', 'senderName': '用户B', 'senderAvatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'timestamp': '今天 上午9:15', 'isRead': true, 'isSelf': false},
    ],
    'conv_private_li': [
      {'id': 'msg_li_1', 'conversationId': 'conv_private_li', 'type': 'text', 'content': '嗨，在吗？', 'senderId': 'user_c', 'senderName': '用户C', 'senderAvatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'timestamp': '今天 上午8:30', 'isRead': true, 'isSelf': false},
      {'id': 'msg_li_2', 'conversationId': 'conv_private_li', 'type': 'text', 'content': '在呢', 'senderId': 'current_user', 'senderName': '我', 'senderAvatar': 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400', 'timestamp': '今天 上午8:32', 'isRead': true, 'isSelf': true},
      {'id': 'msg_li_3', 'conversationId': 'conv_private_li', 'type': 'text', 'content': '我拍了几张照片，发给你看看', 'senderId': 'user_c', 'senderName': '用户C', 'senderAvatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'timestamp': '今天 上午8:35', 'isRead': true, 'isSelf': false},
      {'id': 'msg_li_4', 'conversationId': 'conv_private_li', 'type': 'image', 'content': '图片', 'imageUrl': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=600', 'thumbnailUrl': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200', 'senderId': 'user_c', 'senderName': '用户C', 'senderAvatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'timestamp': '今天 上午8:36', 'isRead': false, 'isSelf': false},
    ],
    'conv_group_photo': [
      {'id': 'msg_group_1', 'conversationId': 'conv_group_photo', 'type': 'text', 'content': '大家好，今天天气不错，适合外拍', 'senderId': 'user_d', 'senderName': '用户D', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '今天 上午9:00', 'isRead': true, 'isSelf': false},
      {'id': 'msg_group_2', 'conversationId': 'conv_group_photo', 'type': 'text', 'content': '我也想去，有人组队吗？', 'senderId': 'user_e', 'senderName': '用户E', 'senderAvatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400', 'timestamp': '今天 上午9:05', 'isRead': true, 'isSelf': false},
      {'id': 'msg_group_3', 'conversationId': 'conv_group_photo', 'type': 'text', 'content': '我可以一起', 'senderId': 'current_user', 'senderName': '我', 'senderAvatar': 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400', 'timestamp': '今天 上午9:10', 'isRead': true, 'isSelf': true},
      {'id': 'msg_group_4', 'conversationId': 'conv_group_photo', 'type': 'image', 'content': '图片', 'imageUrl': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600', 'thumbnailUrl': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=200', 'senderId': 'user_f', 'senderName': '用户F', 'senderAvatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400', 'timestamp': '今天 上午9:15', 'isRead': true, 'isSelf': false},
      {'id': 'msg_group_5', 'conversationId': 'conv_group_photo', 'type': 'text', 'content': '这张照片构图很棒！', 'senderId': 'user_d', 'senderName': '用户D', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '今天 上午9:20', 'isRead': true, 'isSelf': false},
    ],
    'conv_circle_1': [
      {'id': 'msg_c1_1', 'conversationId': 'conv_circle_1', 'type': 'text', 'content': '🔥 推荐秘境 💬 欢迎加入社群😘', 'senderId': 'circle_1', 'senderName': '摄影班交流', 'senderAvatar': 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400', 'timestamp': '2025年12月19日', 'isRead': true, 'isSelf': false},
    ],
    'conv_private_1': [
      {'id': 'msg_p1_1', 'conversationId': 'conv_private_1', 'type': 'text', 'content': '[链接] https://m.tb.cn/h.7WmACZJ?tk=...', 'senderId': 'user_d', 'senderName': '用户D', 'senderAvatar': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400', 'timestamp': '2025年12月18日', 'isRead': true, 'isSelf': false},
    ],
    'conv_encrypted_1': [
      {'id': 'enc1_1', 'conversationId': 'conv_encrypted_1', 'type': 'text', 'content': '这是加密会话内容，仅验证身份后可查看。', 'senderId': 'enc_user_1', 'senderName': '私密项目组', 'senderAvatar': 'https://images.unsplash.com/photo-1614028674026-a65e31bfd27c?w=400', 'timestamp': '2025年12月22日', 'isRead': false, 'isSelf': false},
    ],
    'conv_encrypted_2': [
      {'id': 'enc2_1', 'conversationId': 'conv_encrypted_2', 'type': 'text', 'content': '文件已发送，请注意查收。', 'senderId': 'enc_user_2', 'senderName': '神秘人', 'senderAvatar': 'https://images.unsplash.com/photo-1566492031773-4f4e44671857?w=400', 'timestamp': '昨天', 'isRead': true, 'isSelf': false},
    ],
  };
}
