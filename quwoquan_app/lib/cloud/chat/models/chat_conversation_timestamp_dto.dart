/// [ChatRepository.getConversationTimestamps] 单行（列表增量同步用）。
class ChatConversationTimestampDto {
  const ChatConversationTimestampDto({
    required this.conversationId,
    this.updatedAt,
    this.settingsUpdatedAt,
    this.lastMessageAt,
    this.lastMessageTime,
    this.lastMessagePreview,
    this.unreadCount,
    this.type,
  });

  final String conversationId;
  final String? updatedAt;
  final String? settingsUpdatedAt;
  final String? lastMessageAt;
  final String? lastMessageTime;
  final String? lastMessagePreview;
  final int? unreadCount;
  final String? type;

  factory ChatConversationTimestampDto.fromMap(Map<String, dynamic> m) {
    return ChatConversationTimestampDto(
      conversationId: (m['conversationId'] ?? '').toString(),
      updatedAt: m['updatedAt']?.toString(),
      settingsUpdatedAt: m['settingsUpdatedAt']?.toString(),
      lastMessageAt: m['lastMessageAt']?.toString(),
      lastMessageTime: m['lastMessageTime']?.toString(),
      lastMessagePreview: m['lastMessagePreview']?.toString(),
      unreadCount: (m['unreadCount'] as num?)?.toInt(),
      type: m['type']?.toString(),
    );
  }

  /// 本地缓存 / 搜索同步使用同一 canonical 字段。
  Map<String, dynamic> toMap() => <String, dynamic>{
    'conversationId': conversationId,
    if (updatedAt != null) 'updatedAt': updatedAt,
    if (settingsUpdatedAt != null) 'settingsUpdatedAt': settingsUpdatedAt,
    if (lastMessageAt != null) 'lastMessageAt': lastMessageAt,
    if (lastMessageTime != null) 'lastMessageTime': lastMessageTime,
    if (lastMessagePreview != null) 'lastMessagePreview': lastMessagePreview,
    if (unreadCount != null) 'unreadCount': unreadCount,
    if (type != null) 'type': type,
  };
}
