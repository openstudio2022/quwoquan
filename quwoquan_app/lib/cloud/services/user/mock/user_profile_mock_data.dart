// ignore_for_file: prefer_single_quotes
// 用户主页域 mock 数据（canonical 字段，与 UserProfile 业务对象对齐）。
// 字段命名与 content 域 DTO 保持一致：
// - authorId / displayName / avatarUrl（与 PostBaseDto 共享）
// - works：作品集（id / type / title / coverUrl / likeCount / date / desc）
// - lifeItems：生活记录（id / name / category / categoryKey / coverUrl / desc）
// 待 contracts/metadata/user/service.yaml 定义后，此文件由 make codegen-app 驱动替换。
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

class UserProfileMockData {
  UserProfileMockData._();

  // ─── 用户帖子（与 ContentMockData 同源 DTO，模拟用户自己发的内容）────────────

  static List<PostBaseDto> userPostsFor(String userId) {
    return [
      PhotoPostDto.fromMap({
        'postId': '${userId}_p1',
        'contentType': 'photo',
        'authorId': userId,
        'displayName': _displayNameFor(userId),
        'authorAvatarUrl': _avatarFor(userId),
        'authorBackgroundUrl': _backgroundFor(userId),
        'coverUrl': 'https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400',
        'imageUrls': ['https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=800'],
        'width': 800,
        'height': 600,
        'body': '光影的节奏',
        'likeCount': 1200,
        'commentCount': 45,
        'favoriteCount': 230,
        'shareCount': 18,
        'createdAt': '2025-12-20T10:00:00Z',
      }),
      VideoPostDto.fromMap({
        'postId': '${userId}_v1',
        'contentType': 'video',
        'authorId': userId,
        'displayName': _displayNameFor(userId),
        'authorAvatarUrl': _avatarFor(userId),
        'authorBackgroundUrl': _backgroundFor(userId),
        'videoUrl': 'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4',
        'thumbnailUrl': 'https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400',
        'width': 720,
        'height': 1280,
        'durationMs': 30000,
        'body': '森林的呼吸',
        'likeCount': 840,
        'commentCount': 32,
        'favoriteCount': 140,
        'shareCount': 25,
        'createdAt': '2025-12-15T15:30:00Z',
      }),
      ArticlePostDto.fromMap({
        'postId': '${userId}_a1',
        'contentType': 'article',
        'authorId': userId,
        'displayName': _displayNameFor(userId),
        'authorAvatarUrl': _avatarFor(userId),
        'authorBackgroundUrl': _backgroundFor(userId),
        'title': '极简摄影的真谛',
        'body': '通过剥离不必要的元素，我们才能看见事物的本质。这是一篇关于极简主义摄影的思考与实践。',
        'coverUrl': 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400',
        'likeCount': 2100,
        'commentCount': 78,
        'favoriteCount': 560,
        'shareCount': 43,
        'createdAt': '2025-12-10T09:00:00Z',
      }),
      MomentPostDto.fromMap({
        'postId': '${userId}_m1',
        'contentType': 'moment',
        'authorId': userId,
        'displayName': _displayNameFor(userId),
        'authorAvatarUrl': _avatarFor(userId),
        'authorBackgroundUrl': _backgroundFor(userId),
        'body': '咖啡厅一角，除了香味，还有孤独。',
        'imageUrls': ['https://images.unsplash.com/photo-1650211573412-9d36d0cbbf00?q=80&w=400'],
        'likeCount': 560,
        'commentCount': 18,
        'favoriteCount': 90,
        'shareCount': 12,
        'createdAt': '2025-12-05T20:00:00Z',
      }),
    ];
  }

  // ─── 作品集（Works / Portfolio）────────────────────────────────────────────

  static List<UserWorkItem> worksFor(String userId) {
    return [
      const UserWorkItem(
        id: 'w1',
        type: 'photo',
        title: '光影的节奏',
        coverUrl: 'https://images.unsplash.com/photo-1647956450271-2ff54205bebf?q=80&w=400',
        likeCount: 1200,
        date: '2025-12-20',
        desc: '在布鲁塞尔的午后，捕捉到的一组极简主义建筑光影。',
      ),
      const UserWorkItem(
        id: 'w2',
        type: 'video',
        title: '森林的呼吸',
        coverUrl: 'https://images.unsplash.com/photo-1646034296147-d8ed3aace9a4?q=80&w=400',
        likeCount: 840,
        date: '2025-12-15',
        desc: '4K延时摄影，记录大兴安岭清晨云雾缭绕的过程。',
      ),
      const UserWorkItem(
        id: 'w3',
        type: 'article',
        title: '极简摄影的真谛',
        coverUrl: 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400',
        likeCount: 2100,
        date: '2025-12-10',
        desc: '通过剥离不必要的元素，我们才能看见事物的本质。',
      ),
      const UserWorkItem(
        id: 'w4',
        type: 'photo',
        title: '咖啡厅一角',
        coverUrl: 'https://images.unsplash.com/photo-1650211573412-9d36d0cbbf00?q=80&w=400',
        likeCount: 560,
        date: '2025-12-05',
        desc: '深夜的咖啡馆，除了香味，还有孤独。',
      ),
    ];
  }

  // ─── 生活记录（Life Items）──────────────────────────────────────────────────

  static List<UserLifeItem> lifeItemsFor(String userId) {
    return [
      const UserLifeItem(
        id: 'i1',
        name: '阿那亚礼堂',
        category: '足迹',
        categoryKey: 'footprint',
        coverUrl: 'https://images.unsplash.com/photo-1627216661750-c59a4cea849c?q=80&w=400',
        desc: '在海边的孤独感中寻找创作灵感。',
      ),
      const UserLifeItem(
        id: 'i2',
        name: '《摄影的哲学》',
        category: '书影音',
        categoryKey: 'soul',
        coverUrl: 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?q=80&w=400',
        desc: '比起技巧，我更痴迷于思考快门背后。',
      ),
      const UserLifeItem(
        id: 'i3',
        name: 'Dirty Coffee',
        category: '味蕾',
        categoryKey: 'taste',
        coverUrl: 'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?q=80&w=400',
        desc: '喜欢那种冷热交替的冲突感。',
      ),
      const UserLifeItem(
        id: 'i4',
        name: 'Leica M11',
        category: '爱物',
        categoryKey: 'private',
        coverUrl: 'https://images.unsplash.com/photo-1648049003029-3b3b32cb9a1f?q=80&w=400',
        desc: '它是我身体的延伸。',
      ),
    ];
  }

  // ─── Private helpers ────────────────────────────────────────────────────────

  static String _displayNameFor(String userId) {
    const map = <String, String>{
      'nature_photographer': '自然摄影师',
      'travel_photographer': '旅行摄影师',
      'street_photo': '街头摄影',
      'a1': '楹语小筑',
      'a2': '自然摄影师',
      'tech_daily': 'TechDaily',
      'mo_yun': '墨韵',
      'travel_notes': '旅行笔记',
    };
    return map[userId] ?? userId;
  }

  static String _avatarFor(String userId) {
    const map = <String, String>{
      'nature_photographer': 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      'travel_photographer': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      'street_photo': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      'a1': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      'mo_yun': 'https://images.unsplash.com/photo-1545996124-0501eb292251?w=100',
    };
    return map[userId] ?? 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100';
  }

  static String _backgroundFor(String userId) {
    const map = <String, String>{
      'nature_photographer': 'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
      'travel_photographer': 'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
      'a1': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200',
    };
    return map[userId] ?? 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200';
  }
}

// ─── Value Objects ─────────────────────────────────────────────────────────

/// 作品集条目（待 service.yaml 定义后由 codegen 替换）
class UserWorkItem {
  const UserWorkItem({
    required this.id,
    required this.type,
    required this.title,
    required this.coverUrl,
    required this.likeCount,
    required this.date,
    required this.desc,
  });

  final String id;
  final String type;
  final String title;
  final String coverUrl;
  final int likeCount;
  final String date;
  final String desc;
}

/// 生活记录条目（待 service.yaml 定义后由 codegen 替换）
class UserLifeItem {
  const UserLifeItem({
    required this.id,
    required this.name,
    required this.category,
    required this.categoryKey,
    required this.coverUrl,
    required this.desc,
  });

  final String id;
  final String name;
  final String category;
  final String categoryKey;
  final String coverUrl;
  final String desc;
}
