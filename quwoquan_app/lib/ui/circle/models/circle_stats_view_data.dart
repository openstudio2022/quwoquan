import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';

/// 圈子详情页统计条与摘要行用的强类型视图数据（由 getCircleStats wire + CircleDto 派生）。
class CircleStatsViewData {
  const CircleStatsViewData({
    required this.members,
    required this.posts,
    required this.weeklyActive,
    required this.likes,
  });

  static const empty = CircleStatsViewData(
    members: 0,
    posts: 0,
    weeklyActive: 0,
    likes: 0,
  );

  final int members;
  final int posts;
  final int weeklyActive;
  final int likes;

  factory CircleStatsViewData.fromWire(
    Map<String, dynamic> stats, {
    CircleDto? circleFallback,
  }) {
    int read(String a, String b, int fallback) {
      final v = stats[a] ?? stats[b];
      if (v is num) return v.toInt();
      if (v is String) {
        final p = int.tryParse(v.trim());
        if (p != null) return p;
      }
      return fallback;
    }

    final fb = circleFallback;
    return CircleStatsViewData(
      members: read('members', 'totalMembers', fb?.memberCount ?? 0),
      posts: read('posts', 'totalPosts', fb?.postCount ?? 0),
      weeklyActive: read(
        'weeklyActive',
        'active',
        fb?.weeklyActiveCount ?? 0,
      ),
      likes: read('likes', 'totalLikes', 0),
    );
  }

  /// 详情头 [CircleStatsRow]：帖子/成员/周活以 [CircleDto] 为准，点赞保留 wire。
  CircleStatsViewData forDetailRow(CircleDto? circle) {
    if (circle == null) return this;
    return CircleStatsViewData(
      members: circle.memberCount,
      posts: circle.postCount,
      weeklyActive: circle.weeklyActiveCount,
      likes: likes,
    );
  }
}
