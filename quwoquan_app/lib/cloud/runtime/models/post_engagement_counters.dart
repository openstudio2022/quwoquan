import 'package:meta/meta.dart';

/// 帖子聚合计数（GetCounters 响应；字段以 wire 为准，缺省为 0）。
@immutable
class PostEngagementCounters {
  const PostEngagementCounters({
    required this.likeCount,
    required this.commentCount,
    this.favoriteCount = 0,
    this.shareCount = 0,
  });

  final int likeCount;
  final int commentCount;
  final int favoriteCount;
  final int shareCount;

  factory PostEngagementCounters.fromMap(Map<String, dynamic> m) {
    int n(Object? v) => (v is num) ? v.toInt() : int.tryParse('$v') ?? 0;

    return PostEngagementCounters(
      likeCount: n(m['likeCount'] ?? m['likesCount'] ?? m['likes']),
      commentCount: n(
        m['commentCount'] ?? m['commentsCount'] ?? m['comments'],
      ),
      favoriteCount: n(
        m['favoriteCount'] ?? m['savesCount'] ?? m['bookmarks'],
      ),
      shareCount: n(m['shareCount'] ?? m['shares']),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PostEngagementCounters &&
          runtimeType == other.runtimeType &&
          likeCount == other.likeCount &&
          commentCount == other.commentCount &&
          favoriteCount == other.favoriteCount &&
          shareCount == other.shareCount;

  @override
  int get hashCode =>
      Object.hash(likeCount, commentCount, favoriteCount, shareCount);
}
