import 'dart:async';
import 'dart:math';

/// 数据服务接口
abstract class DataService {
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  });

  Future<Map<String, dynamic>> getDataItem({
    required String endpoint,
    required String id,
    Map<String, dynamic>? params,
  });

  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  });

  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  });

  Future<void> deleteDataItem({
    required String endpoint,
    required String id,
  });
}

/// 数据服务实现 - 基于原型代码的 MockDataService
class DataServiceImpl implements DataService {
  // 模拟用户数据
  final Map<String, Map<String, dynamic>> _mockUsers = {
    'nature_photographer': {
      'id': 'user_001',
      'username': 'nature_photographer',
      'displayName': '不再举杯邀明月',
      'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&h=150&fit=crop&crop=face',
      'bio': '关心时事、关注新闻、思考人生、思索生命',
      'location': 'IP属地: 四川',
      'followers': 17000,
      'following': 158,
      'likes': 220000,
      'isFollowing': false,
      'verified': true,
      'postCount': 42,
    },
    'travel_photographer': {
      'id': 'user_002',
      'username': 'travel_photographer',
      'displayName': '旅行摄影师',
      'avatar': 'https://images.unsplash.com/photo-1494790108755-2616b612b1d4?w=150&h=150&fit=crop&crop=face',
      'bio': '✈️ 环球旅行摄影师\n📍 已走过40+国家\n📷 用镜头记录世界之美',
      'location': 'IP属地: 北京',
      'followers': 8200,
      'following': 156,
      'likes': 120000,
      'isFollowing': true,
      'verified': false,
      'postCount': 28,
    },
    'art_creator': {
      'id': 'user_003',
      'username': 'art_creator',
      'displayName': '艺术创作者',
      'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=150&h=150&fit=crop&crop=face',
      'bio': '🎨 数字艺术家\n💭 创意无界限\n✨ 分享灵感与创作',
      'location': 'IP属地: 上海',
      'followers': 3400,
      'following': 245,
      'likes': 89000,
      'isFollowing': false,
      'verified': false,
      'postCount': 15,
    },
    'quwooo_official': {
      'id': 'user_004',
      'username': 'quwooo_official',
      'displayName': '趣我圈官方',
      'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&h=150&fit=crop&crop=face',
      'bio': '🎯 趣我圈官方账号\n📢 新功能与活动发布\n🤝 与用户共建美好社区',
      'location': 'IP属地: 深圳',
      'followers': 156000,
      'following': 0,
      'likes': 2000000,
      'isFollowing': true,
      'verified': true,
      'postCount': 89,
    },
    'foodie_life': {
      'id': 'user_005',
      'username': 'foodie_life',
      'displayName': '美食生活家',
      'avatar': 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&h=150&fit=crop&crop=face',
      'bio': '🍝 意式料理爱好者\n📱 美食博主\n🥘 分享生活中的美味时刻',
      'location': 'IP属地: 广州',
      'followers': 8930,
      'following': 156,
      'likes': 156000,
      'isFollowing': true,
      'verified': false,
      'postCount': 33,
    },
  };

  // 预定义的图片URL池 - 使用稳定的图片服务
  final List<String> _imagePool = [
    'https://picsum.photos/800/800?random=1',
    'https://picsum.photos/800/800?random=2',
    'https://picsum.photos/800/800?random=3',
    'https://picsum.photos/800/800?random=4',
    'https://picsum.photos/800/800?random=5',
    'https://picsum.photos/800/800?random=6',
    'https://picsum.photos/800/800?random=7',
    'https://picsum.photos/800/800?random=8',
    'https://picsum.photos/800/800?random=9',
    'https://picsum.photos/800/800?random=10',
    'https://picsum.photos/800/800?random=11',
    'https://picsum.photos/800/800?random=12',
    'https://picsum.photos/800/800?random=13',
    'https://picsum.photos/800/800?random=14',
    'https://picsum.photos/800/800?random=15',
  ];

  @override
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  }) async {
    // 模拟网络延迟
    await Future.delayed(const Duration(milliseconds: 500));
    
    if (endpoint == '/posts') {
      return _generateMockPosts(limit ?? 20, params?['category'] as String?);
    }
    
    return [];
  }

  @override
  Future<Map<String, dynamic>> getDataItem({
    required String endpoint,
    required String id,
    Map<String, dynamic>? params,
  }) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return {'id': id, 'name': 'Mock Item $id'};
  }

  @override
  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  }) async {
    await Future.delayed(const Duration(milliseconds: 500));
    return {'id': 'new_id_${DateTime.now().millisecondsSinceEpoch}', ...data};
  }

  @override
  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  }) async {
    await Future.delayed(const Duration(milliseconds: 500));
    return {'id': id, ...data};
  }

  @override
  Future<void> deleteDataItem({
    required String endpoint,
    required String id,
  }) async {
    await Future.delayed(const Duration(milliseconds: 500));
    return;
  }

  /// 生成模拟帖子数据 - 基于原型代码的逻辑
  List<Map<String, dynamic>> _generateMockPosts(int count, String? category) {
    final posts = <Map<String, dynamic>>[];
    final random = Random();
    final userEntries = _mockUsers.entries.toList();
    
    for (int index = 0; index < count; index++) {
      final userEntry = userEntries[index % userEntries.length];
      final user = userEntry.value;
      final username = userEntry.key;
      
      // 根据分类决定帖子类型
      final postType = _getPostTypeForCategory(category, index);
      final isImage = postType == 'image';
      final isVideo = postType == 'video';
      
      // 生成图片数量（single: 1, carousel: 2-5, grid: 2-4）
      final displayType = _getDisplayType(index);
      final imageCount = displayType == 'single' 
          ? 1 
          : (displayType == 'carousel' 
              ? random.nextInt(4) + 2 
              : random.nextInt(3) + 2);
      
      final post = <String, dynamic>{
        'id': 'post_${category ?? 'all'}_$index',
        'type': postType,
        'username': username,
        'displayName': user['displayName'],
        'avatarUrl': user['avatar'],
        'avatar': user['avatar'], // 兼容字段
        'authorId': user['id'] as String? ?? username,
        'createdAt': DateTime.now()
            .subtract(Duration(hours: index % 24))
            .toIso8601String(),
        'timeAgo': '${(index % 24) + 1}小时前',
        'likes': 100 + index * 10 + random.nextInt(1000),
        'comments': 20 + index + random.nextInt(50),
        'commentsCount': 20 + index + random.nextInt(50),
        'bookmarks': 5 + index + random.nextInt(100),
        'shares': 2 + index + random.nextInt(50),
        'isVerified': user['verified'] as bool? ?? false,
        'location': user['location'] as String?,
        'tags': _generateTags(category),
        'publisher': {
          'type': 'author',
          'id': user['id'] as String? ?? username,
          'username': username,
          'avatar': user['avatar'],
          'verified': user['verified'] as bool? ?? false,
        },
      };
      
      // 生成内容
      if (isImage) {
        // 图片帖子
        final images = List.generate(
          imageCount,
          (i) => _imagePool[(index * imageCount + i) % _imagePool.length],
        );
        post['images'] = images;
        post['displayType'] = displayType;
        post['caption'] = _generateCaption(category, index);
      } else if (isVideo) {
        // 视频帖子
        post['videoUrl'] = 'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4';
        post['videoType'] = index % 2 == 0 ? 'vertical' : 'horizontal';
        post['thumbnailUrl'] = _imagePool[index % _imagePool.length];
        post['duration'] = 30 + index * 5;
        post['caption'] = _generateCaption(category, index);
      }
      
      // 根据分类过滤
      if (category != null && category != 'following' && category != 'recommended') {
        if (category == 'images' && !isImage) continue;
        if (category == 'video' && !isVideo) continue;
      }
      
      posts.add(post);
    }
    
    return posts;
  }
  
  String _getPostTypeForCategory(String? category, int index) {
    if (category == 'images') {
      return 'image';
    } else if (category == 'video') {
      return 'video';
    } else {
      // 混合类型：根据索引决定
      return index % 3 == 0 ? 'video' : 'image';
    }
  }
  
  String _getDisplayType(int index) {
    final types = ['single', 'carousel', 'grid'];
    return types[index % types.length];
  }
  
  List<String> _generateTags(String? category) {
    final tagMap = {
      'images': ['摄影', '图片', '视觉'],
      'video': ['视频', '创作', '分享'],
      'following': ['关注', '推荐'],
      'recommended': ['推荐', '发现'],
    };
    
    return tagMap[category] ?? ['生活', '分享'];
  }
  
  String _generateCaption(String? category, int index) {
    final captions = {
      'images': [
        '今天在山里拍到的美丽日落，大自然总是能给我们最好的礼物 🌅',
        '这次旅行收获满满！每一个角落都有不同的美景等待发现 ✈️📸',
        '用镜头记录生活中的美好瞬间 📷',
      ],
      'video': [
        '精彩视频分享 🎬',
        '记录生活的美好时刻 ✨',
        '创作灵感分享 💡',
      ],
      'following': [
        '关注的内容更新 📢',
        '朋友的最新动态 👥',
      ],
      'recommended': [
        '推荐给你精彩内容 ⭐',
        '发现更多有趣内容 🔍',
      ],
    };
    
    final categoryCaptions = captions[category] ?? ['分享生活中的美好时刻 ✨'];
    return categoryCaptions[index % categoryCaptions.length];
  }
}
