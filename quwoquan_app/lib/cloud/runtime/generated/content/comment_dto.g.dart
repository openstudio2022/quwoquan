// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/fields.yaml (entities.Comment)
// plus wire aliases for API/Mock payloads (profileSubjectId, displayName, etc.).
// Regenerate: make codegen-app

class CommentDto {
  const CommentDto({
    required this.id,
    required this.postId,
    required this.authorId,
    this.personaId,
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
  final String? personaId;
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

  factory CommentDto.fromMap(Map<String, dynamic> m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['profileSubjectId'] ?? m['authorId'] ?? '').toString(),
      personaId: (m['personaId'] ?? m['subAccountId'])?.toString(),
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

  Map<String, dynamic> toMap() => {
        'id': id,
        'postId': postId,
        'authorId': authorId,
        'profileSubjectId': authorId,
        'personaId': personaId,
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
      personaId: personaId,
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
