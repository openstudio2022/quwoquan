import 'package:meta/meta.dart';

/// 用户与帖子的互动状态（对齐 metadata `ContentReaction` 的 API 可读子集）。
@immutable
class ContentReactionState {
  const ContentReactionState({
    required this.postId,
    required this.userId,
    required this.liked,
    required this.favorited,
    this.shared = false,
    this.reported = false,
    this.likedAt,
    this.favoritedAt,
    this.updatedAt,
  });

  final String postId;
  final String userId;
  final bool liked;
  final bool favorited;
  final bool shared;
  final bool reported;
  final DateTime? likedAt;
  final DateTime? favoritedAt;
  final DateTime? updatedAt;

  factory ContentReactionState.fromMap(Map<String, dynamic> m) {
    DateTime? parseTs(Object? v) =>
        DateTime.tryParse(v?.toString() ?? '')?.toUtc();

    return ContentReactionState(
      postId: (m['postId'] ?? '').toString(),
      userId: (m['userId'] ?? m['profileSubjectId'] ?? '').toString(),
      liked: m['liked'] == true,
      favorited: m['favorited'] == true,
      shared: m['shared'] == true,
      reported: m['reported'] == true,
      likedAt: parseTs(m['likedAt']),
      favoritedAt: parseTs(m['favoritedAt']),
      updatedAt: parseTs(m['updatedAt']),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ContentReactionState &&
          runtimeType == other.runtimeType &&
          postId == other.postId &&
          userId == other.userId &&
          liked == other.liked &&
          favorited == other.favorited &&
          shared == other.shared &&
          reported == other.reported &&
          likedAt == other.likedAt &&
          favoritedAt == other.favoritedAt &&
          updatedAt == other.updatedAt;

  @override
  int get hashCode => Object.hash(
    postId,
    userId,
    liked,
    favorited,
    shared,
    reported,
    likedAt,
    favoritedAt,
    updatedAt,
  );
}
