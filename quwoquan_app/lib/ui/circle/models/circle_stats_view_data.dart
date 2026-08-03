import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子详情页统计条与摘要行用的强类型视图数据（由 getCircleStats wire + CircleDto 派生）。
class CircleStatsViewData {
  const CircleStatsViewData({
    required this.members,
    required this.posts,
    required this.discussions,
    required this.weeklyActive,
    required this.likes,
    this.storageUsedBytes = 0,
    this.storageQuotaBytes = 0,
  });

  static const empty = CircleStatsViewData(
    members: 0,
    posts: 0,
    discussions: 0,
    weeklyActive: 0,
    likes: 0,
  );

  final int members;
  final int posts;
  final int discussions;
  final int weeklyActive;
  final int likes;

  /// 圈子文件板块容量（stats wire `storageUsedBytes/storageQuotaBytes`）。
  final int storageUsedBytes;
  final int storageQuotaBytes;

  factory CircleStatsViewData.fromWire(CircleStatsWire wire) {
    return CircleStatsViewData(
      members: wire.memberCount,
      posts: wire.postCount,
      discussions: wire.discussionCount,
      weeklyActive: wire.weeklyActiveCount,
      likes: wire.likeCount,
      storageUsedBytes: wire.storageUsedBytes,
      storageQuotaBytes: wire.storageQuotaBytes,
    );
  }

  /// 详情头 [CircleStatsRow]：帖子/成员/周活以 [CircleDto] 为准，点赞保留 wire。
  CircleStatsViewData forDetailRow(CircleDto? circle) {
    if (circle == null) return this;
    return CircleStatsViewData(
      members: circle.memberCount,
      posts: circle.postCount,
      discussions: discussions,
      weeklyActive: circle.weeklyActiveCount,
      likes: likes,
      storageUsedBytes: storageUsedBytes,
      storageQuotaBytes: storageQuotaBytes,
    );
  }
}
