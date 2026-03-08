/// Typed DTO for the ConversationUserState entity.
/// Maps to contracts/metadata/messages/conversation/fields.yaml → ConversationUserState.
class ConversationUserStateDto {
  final String id;
  final String userId;
  final String conversationId;
  final int readSeq;
  final int unreadCount;
  final bool muted;
  final bool pinned;
  final DateTime? lastReadAt;
  final DateTime updatedAt;

  const ConversationUserStateDto({
    required this.id,
    required this.userId,
    required this.conversationId,
    required this.readSeq,
    required this.unreadCount,
    required this.muted,
    required this.pinned,
    this.lastReadAt,
    required this.updatedAt,
  });

  factory ConversationUserStateDto.fromMap(Map<String, dynamic> map) {
    return ConversationUserStateDto(
      id: (map['_id'] ?? map['id'] ?? '') as String,
      userId: (map['userId'] ?? '') as String,
      conversationId: (map['conversationId'] ?? '') as String,
      readSeq: (map['readSeq'] as num?)?.toInt() ?? 0,
      unreadCount: (map['unreadCount'] as num?)?.toInt() ?? 0,
      muted: (map['muted'] as bool?) ?? false,
      pinned: (map['pinned'] as bool?) ?? false,
      lastReadAt: map['lastReadAt'] != null
          ? DateTime.tryParse(map['lastReadAt'] as String)
          : null,
      updatedAt: DateTime.tryParse((map['updatedAt'] ?? '') as String) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'userId': userId,
        'conversationId': conversationId,
        'readSeq': readSeq,
        'unreadCount': unreadCount,
        'muted': muted,
        'pinned': pinned,
        if (lastReadAt != null) 'lastReadAt': lastReadAt!.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
      };
}
