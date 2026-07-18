import 'package:meta/meta.dart';

/// 帖子聚合计数（GetCounters 响应；字段以 wire 为准，缺省为 0）。
@immutable
class PostEngagementCounters {
  const PostEngagementCounters({
    required this.likeCount,
    required this.commentCount,
    this.shareCount = 0,
  });

  final int likeCount;
  final int commentCount;
  final int shareCount;

  factory PostEngagementCounters.fromMap(Map<String, dynamic> m) {
    int n(Object? v) => (v is num) ? v.toInt() : int.tryParse('$v') ?? 0;

    return PostEngagementCounters(
      likeCount: n(m['likeCount']),
      commentCount: n(m['commentCount']),
      shareCount: n(m['shareCount']),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PostEngagementCounters &&
          runtimeType == other.runtimeType &&
          likeCount == other.likeCount &&
          commentCount == other.commentCount &&
          shareCount == other.shareCount;

  @override
  int get hashCode => Object.hash(likeCount, commentCount, shareCount);
}
