import 'dart:math' as math;

class PostInteractionInput {
  const PostInteractionInput({
    this.scopePostIds = const <String>{},
    this.likedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.shareCounts = const <String, int>{},
    this.commentCounts = const <String, int>{},
  });

  final Set<String> scopePostIds;
  final Set<String> likedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> shareCounts;
  final Map<String, int> commentCounts;

  Set<String> get effectiveScopePostIds {
    if (scopePostIds.isNotEmpty) {
      return scopePostIds;
    }
    return <String>{
      ...likedPostIds,
      ...likeCounts.keys,
      ...shareCounts.keys,
      ...commentCounts.keys,
    };
  }
}

class PostInteractionState {
  const PostInteractionState({
    this.likedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.confirmedShareCounts = const <String, int>{},
    this.confirmedCommentCounts = const <String, int>{},
    this.pendingCommentDeltas = const <String, int>{},
  });

  final Set<String> likedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> confirmedShareCounts;
  final Map<String, int> confirmedCommentCounts;
  final Map<String, int> pendingCommentDeltas;

  bool isLiked(String postId) => likedPostIds.contains(postId);

  bool hasLikeStateFor(String postId) {
    return likedPostIds.contains(postId) || likeCounts.containsKey(postId);
  }

  int likeCountFor(String postId, {int fallback = 0}) {
    return likeCounts[postId] ?? fallback;
  }

  int shareCountFor(String postId, {int fallback = 0}) {
    return confirmedShareCounts[postId] ?? fallback;
  }

  int commentCountFor(String postId, {int fallback = 0}) {
    final confirmed = confirmedCommentCounts[postId] ?? fallback;
    final pending = pendingCommentDeltas[postId] ?? 0;
    return math.max(0, confirmed + pending);
  }

  PostInteractionState copyWith({
    Set<String>? likedPostIds,
    Map<String, int>? likeCounts,
    Map<String, int>? confirmedShareCounts,
    Map<String, int>? confirmedCommentCounts,
    Map<String, int>? pendingCommentDeltas,
  }) {
    return PostInteractionState(
      likedPostIds: likedPostIds ?? this.likedPostIds,
      likeCounts: likeCounts ?? this.likeCounts,
      confirmedShareCounts: confirmedShareCounts ?? this.confirmedShareCounts,
      confirmedCommentCounts:
          confirmedCommentCounts ?? this.confirmedCommentCounts,
      pendingCommentDeltas: pendingCommentDeltas ?? this.pendingCommentDeltas,
    );
  }

  factory PostInteractionState.fromMap(Map<String, dynamic> map) {
    Set<String> readSet(String key) {
      final raw = map[key];
      if (raw is List) {
        return raw.map((item) => item.toString()).toSet();
      }
      return const <String>{};
    }

    Map<String, int> readIntMap(String key) {
      final raw = map[key];
      if (raw is Map) {
        return raw.map(
          (entryKey, value) => MapEntry(
            entryKey.toString(),
            value is num ? value.toInt() : int.tryParse(value.toString()) ?? 0,
          ),
        );
      }
      return const <String, int>{};
    }

    return PostInteractionState(
      likedPostIds: readSet('likedPostIds'),
      likeCounts: readIntMap('likeCounts'),
      confirmedShareCounts: readIntMap('confirmedShareCounts'),
      confirmedCommentCounts: readIntMap('confirmedCommentCounts').isNotEmpty
          ? readIntMap('confirmedCommentCounts')
          : readIntMap('commentCounts'),
      pendingCommentDeltas: readIntMap('pendingCommentDeltas'),
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'likedPostIds': likedPostIds.toList(growable: false),
      'likeCounts': likeCounts,
      'confirmedShareCounts': confirmedShareCounts,
      'confirmedCommentCounts': confirmedCommentCounts,
      'pendingCommentDeltas': pendingCommentDeltas,
    };
  }
}
