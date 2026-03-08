/// Typed DTO for the ConversationMember entity.
/// Maps to contracts/metadata/messages/conversation/fields.yaml → ConversationMember.
class ConversationMemberDto {
  final String id;
  final String conversationId;
  final String userId;
  final String? displayName;
  final String? avatarUrl;
  final String memberType;
  final String role;
  final String? assistantSkillId;
  final String? invitedBy;
  final DateTime joinedAt;

  const ConversationMemberDto({
    required this.id,
    required this.conversationId,
    required this.userId,
    this.displayName,
    this.avatarUrl,
    required this.memberType,
    required this.role,
    this.assistantSkillId,
    this.invitedBy,
    required this.joinedAt,
  });

  factory ConversationMemberDto.fromMap(Map<String, dynamic> map) {
    return ConversationMemberDto(
      id: (map['_id'] ?? map['id'] ?? '') as String,
      conversationId: (map['conversationId'] ?? '') as String,
      userId: (map['userId'] ?? '') as String,
      displayName: map['displayName'] as String?,
      avatarUrl: map['avatarUrl'] as String?,
      memberType: (map['memberType'] ?? 'user') as String,
      role: (map['role'] ?? 'member') as String,
      assistantSkillId: map['assistantSkillId'] as String?,
      invitedBy: map['invitedBy'] as String?,
      joinedAt: DateTime.tryParse((map['joinedAt'] ?? '') as String) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
        'id': id,
        'conversationId': conversationId,
        'userId': userId,
        if (displayName != null) 'displayName': displayName,
        if (avatarUrl != null) 'avatarUrl': avatarUrl,
        'memberType': memberType,
        'role': role,
        if (assistantSkillId != null) 'assistantSkillId': assistantSkillId,
        if (invitedBy != null) 'invitedBy': invitedBy,
        'joinedAt': joinedAt.toIso8601String(),
      };
}
