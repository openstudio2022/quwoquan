import 'package:meta/meta.dart';

/// 用户与帖子的互动状态（对齐 metadata `ContentReaction` 的 API 可读子集）。
@immutable
class ContentReactionState {
  const ContentReactionState({
    required this.postId,
    required this.userId,
    required this.liked,
    this.shared = false,
    this.reported = false,
    this.likedAt,
    this.updatedAt,
  });

  final String postId;
  final String userId;
  final bool liked;
  final bool shared;
  final bool reported;
  final DateTime? likedAt;
  final DateTime? updatedAt;

  factory ContentReactionState.fromMap(Map<String, dynamic> m) {
    DateTime? parseTs(Object? v) =>
        DateTime.tryParse(v?.toString() ?? '')?.toUtc();

    return ContentReactionState(
      postId: (m['postId'] ?? '').toString(),
      userId: (m['userId'] ?? m['profileSubjectId'] ?? '').toString(),
      liked: m['liked'] == true,
      shared: m['shared'] == true,
      reported: m['reported'] == true,
      likedAt: parseTs(m['likedAt']),
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
          shared == other.shared &&
          reported == other.reported &&
          likedAt == other.likedAt &&
          updatedAt == other.updatedAt;

  @override
  int get hashCode => Object.hash(
    postId,
    userId,
    liked,
    shared,
    reported,
    likedAt,
    updatedAt,
  );
}
