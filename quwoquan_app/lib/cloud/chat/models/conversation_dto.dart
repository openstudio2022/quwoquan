/// Typed DTO for the Conversation entity.
/// Maps to contracts/metadata/messages/conversation/fields.yaml → Conversation.
class ConversationDto {
  final String id;
  final String type;
  final String? title;
  final String? avatarUrl;
  final String? groupAvatarUrl;
  final int groupAvatarVersion;
  final String creatorId;
  final String? circleId;
  final int maxSeq;
  final int memberCount;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String? lastMessageId;
  final String? lastMessagePreview;
  final DateTime? lastMessageTime;
  final int messageCount;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;
  /// 群成员名册版本（Mock/部分 wire 扩展字段）。
  final int? membersRosterRevision;

  const ConversationDto({
    required this.id,
    required this.type,
    this.title,
    this.avatarUrl,
    this.groupAvatarUrl,
    this.groupAvatarVersion = 0,
    required this.creatorId,
    this.circleId,
    required this.maxSeq,
    required this.memberCount,
    required this.maxGroupSize,
    required this.receiptEnabled,
    this.lastMessageId,
    this.lastMessagePreview,
    this.lastMessageTime,
    required this.messageCount,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.membersRosterRevision,
  });

  factory ConversationDto.fromMap(Map<String, dynamic> map) {
    return ConversationDto(
      id: (map['_id'] ?? map['id'] ?? '') as String,
      type: (map['type'] ?? 'direct') as String,
      title: map['title'] as String?,
      avatarUrl: map['avatarUrl'] as String?,
      groupAvatarUrl: map['groupAvatarUrl'] as String?,
      groupAvatarVersion: (map['groupAvatarVersion'] as num?)?.toInt() ?? 0,
      creatorId: (map['creatorId'] ?? '') as String,
      circleId: map['circleId'] as String?,
      maxSeq: (map['maxSeq'] as num?)?.toInt() ?? 0,
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      maxGroupSize: (map['maxGroupSize'] as num?)?.toInt() ?? 1000,
      receiptEnabled: (map['receiptEnabled'] as bool?) ?? true,
      lastMessageId: map['lastMessageId'] as String?,
      lastMessagePreview: map['lastMessagePreview'] as String?,
      lastMessageTime: map['lastMessageTime'] != null
          ? DateTime.tryParse(map['lastMessageTime'] as String)
          : null,
      messageCount: (map['messageCount'] as num?)?.toInt() ?? 0,
      status: (map['status'] ?? 'active') as String,
      createdAt: DateTime.tryParse((map['createdAt'] ?? '') as String) ??
          DateTime.now(),
      updatedAt: DateTime.tryParse((map['updatedAt'] ?? '') as String) ??
          DateTime.now(),
      membersRosterRevision: (map['membersRosterRevision'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toMap() => {
        '_id': id,
        'id': id,
        'type': type,
        if (title != null) 'title': title,
        if (avatarUrl != null) 'avatarUrl': avatarUrl,
        if (groupAvatarUrl != null) 'groupAvatarUrl': groupAvatarUrl,
        'groupAvatarVersion': groupAvatarVersion,
        'creatorId': creatorId,
        if (circleId != null) 'circleId': circleId,
        'maxSeq': maxSeq,
        'memberCount': memberCount,
        'maxGroupSize': maxGroupSize,
        'receiptEnabled': receiptEnabled,
        if (lastMessageId != null) 'lastMessageId': lastMessageId,
        if (lastMessagePreview != null)
          'lastMessagePreview': lastMessagePreview,
        if (lastMessageTime != null) ...{
          'lastMessageTime': lastMessageTime!.toIso8601String(),
          'lastMessageAt': lastMessageTime!.toIso8601String(),
        },
        'messageCount': messageCount,
        'status': status,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
        if (membersRosterRevision != null)
          'membersRosterRevision': membersRosterRevision,
      };
}
