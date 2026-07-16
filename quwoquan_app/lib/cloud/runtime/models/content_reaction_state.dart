import 'package:meta/meta.dart';

/// 用户与帖子的互动状态（对齐 metadata `ContentReaction` 的 API 可读子集）。
@immutable
class ContentReactionState {
  const ContentReactionState({
    required this.found,
    required this.postId,
    required this.liked,
    required this.version,
    this.updatedAt,
  });

  final bool found;
  final String postId;
  final bool liked;
  final int version;
  final DateTime? updatedAt;

  factory ContentReactionState.fromMap(Map<String, dynamic> m) {
    const allowedFields = <String>{
      'found',
      'postId',
      'liked',
      'version',
      'updatedAt',
    };
    if (m.keys.any((key) => !allowedFields.contains(key))) {
      throw const FormatException('unknown ContentReactionState field');
    }
    final found = m['found'];
    final postId = m['postId'];
    final liked = m['liked'];
    final version = m['version'];
    if (found is! bool ||
        postId is! String ||
        postId.trim().isEmpty ||
        liked is! bool ||
        version is! num ||
        version.toInt() != version) {
      throw const FormatException('invalid ContentReactionState payload');
    }
    final rawUpdatedAt = m['updatedAt'];
    final updatedAt = rawUpdatedAt == null
        ? null
        : DateTime.tryParse(
            rawUpdatedAt is String ? rawUpdatedAt : '',
          )?.toUtc();
    if (rawUpdatedAt != null && updatedAt == null) {
      throw const FormatException('invalid ContentReactionState.updatedAt');
    }

    return ContentReactionState(
      found: found,
      postId: postId,
      liked: liked,
      version: version.toInt(),
      updatedAt: updatedAt,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ContentReactionState &&
          runtimeType == other.runtimeType &&
          found == other.found &&
          postId == other.postId &&
          liked == other.liked &&
          version == other.version &&
          updatedAt == other.updatedAt;

  @override
  int get hashCode => Object.hash(found, postId, liked, version, updatedAt);
}
