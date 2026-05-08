// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.Comment)
// plus wire aliases for API/Mock payloads (displayName, avatar snapshots, etc.).
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';

class CommentDto {
  const CommentDto({
    required this.id,
    required this.postId,
    required this.authorId,
    this.displayName,
    this.avatarUrl,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.replyToDisplayName,
    this.replyCount = 0,
    this.likeCount = 0,
    this.status = 'visible',
    this.isAuthor = false,
    this.personaContextVersion,
    required this.createdAt,
  });

  final String id;
  final String postId;
  final String authorId;
  final String? displayName;
  final String? avatarUrl;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final int replyCount;
  final int likeCount;
  final String status;
  final bool isAuthor;
  final int? personaContextVersion;
  final DateTime createdAt;

  factory CommentDto.fromMap(CloudJsonMap m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['authorId'] ?? m['subAccountId'] ?? '').toString(),
      displayName: (m['authorDisplayNameSnapshot'] ?? m['displayName'])
          ?.toString(),
      avatarUrl: (m['authorAvatarUrlSnapshot'] ?? m['avatarUrl'])?.toString(),
      content: (m['content'] ?? '').toString(),
      replyToCommentId: m['replyToCommentId']?.toString(),
      replyToUserId: m['replyToUserId']?.toString(),
      replyToDisplayName: m['replyToDisplayName']?.toString(),
      replyCount: (m['replyCount'] as num?)?.toInt() ?? 0,
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      status: (m['status'] ?? 'visible').toString(),
      isAuthor: m['isAuthor'] == true,
      personaContextVersion: (m['personaContextVersion'] as num?)?.toInt(),
      createdAt:
          DateTime.tryParse(m['createdAt']?.toString() ?? '') ?? DateTime.now(),
    );
  }

  CloudJsonMap toMap() => {
        'id': id,
        'postId': postId,
        'authorId': authorId,
        'displayName': displayName,
        'authorDisplayNameSnapshot': displayName,
        'avatarUrl': avatarUrl,
        'authorAvatarUrlSnapshot': avatarUrl,
        'content': content,
        'replyToCommentId': replyToCommentId,
        'replyToUserId': replyToUserId,
        'replyToDisplayName': replyToDisplayName,
        'replyCount': replyCount,
        'likeCount': likeCount,
        'status': status,
        'isAuthor': isAuthor,
        if (personaContextVersion != null)
          'personaContextVersion': personaContextVersion,
        'createdAt': createdAt.toIso8601String(),
      };

  CommentDto copyWith({int? replyCount, int? likeCount, String? status}) {
    return CommentDto(
      id: id,
      postId: postId,
      authorId: authorId,
      displayName: displayName,
      avatarUrl: avatarUrl,
      content: content,
      replyToCommentId: replyToCommentId,
      replyToUserId: replyToUserId,
      replyToDisplayName: replyToDisplayName,
      replyCount: replyCount ?? this.replyCount,
      likeCount: likeCount ?? this.likeCount,
      status: status ?? this.status,
      isAuthor: isAuthor,
      personaContextVersion: personaContextVersion,
      createdAt: createdAt,
    );
  }
}
