import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_stats_wire_dto.dart';

int _readStatsInt(
  Map<String, dynamic> stats,
  String a,
  String b,
  int fallback,
) {
  final v = stats[a] ?? stats[b];
  if (v is num) return v.toInt();
  if (v is String) {
    final p = int.tryParse(v.trim());
    if (p != null) return p;
  }
  return fallback;
}

/// 将 stats wire 的松散键收敛为展示用整数（避免 UI 散写 `raw[...]`）。
extension CircleStatsWireProjection on CircleStatsWireDto {
  CircleStatsViewData toViewData({CircleDto? circleFallback}) {
    final s = raw;
    final fb = circleFallback;
    return CircleStatsViewData(
      members: _readStatsInt(s, 'members', 'totalMembers', fb?.memberCount ?? 0),
      posts: _readStatsInt(s, 'posts', 'totalPosts', fb?.postCount ?? 0),
      weeklyActive: _readStatsInt(
        s,
        'weeklyActive',
        'active',
        fb?.weeklyActiveCount ?? 0,
      ),
      likes: _readStatsInt(s, 'likes', 'totalLikes', 0),
    );
  }
}

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

  factory CircleStatsViewData.fromStatsWire(
    CircleStatsWireDto wire, {
    CircleDto? circleFallback,
  }) {
    return wire.toViewData(circleFallback: circleFallback);
  }

  factory CircleStatsViewData.fromWire(
    Map<String, dynamic> stats, {
    CircleDto? circleFallback,
  }) {
    return CircleStatsWireDto.fromMap(stats).toViewData(
      circleFallback: circleFallback,
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
