/// 联系人本地检索结果行（chat 本地检索单轨 ViewData）。
///
/// 数据只来自本地 sqlite 索引，不承担 Cloud wire 或 transport DTO 语义。
class ChatContactSearchItemViewData {
  const ChatContactSearchItemViewData({
    this.contactId = '',
    this.userHandle = '',
    this.displayName = '',
    this.avatarUrl,
    this.conversationId,
    this.conversationType,
    this.source,
    this.subtitle,
    this.highlightText,
    this.matchedField,
  });

  final String contactId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final String? conversationId;
  final String? conversationType;
  final String? source;
  final String? subtitle;
  final String? highlightText;
  final String? matchedField;

  ChatContactSearchItemViewData copyWith({
    String? contactId,
    String? userHandle,
    String? displayName,
    String? avatarUrl,
    String? conversationId,
    String? conversationType,
    String? source,
    String? subtitle,
    String? highlightText,
    String? matchedField,
  }) {
    return ChatContactSearchItemViewData(
      contactId: contactId ?? this.contactId,
      userHandle: userHandle ?? this.userHandle,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      conversationId: conversationId ?? this.conversationId,
      conversationType: conversationType ?? this.conversationType,
      source: source ?? this.source,
      subtitle: subtitle ?? this.subtitle,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'contactId': contactId,
      'userHandle': userHandle,
      'displayName': displayName,
      'avatarUrl': avatarUrl,
      'conversationId': conversationId,
      'conversationType': conversationType,
      'source': source,
      'subtitle': subtitle,
      'highlightText': highlightText,
      'matchedField': matchedField,
    };
  }
}

class ConversationSearchItemView {
  const ConversationSearchItemView({
    required this.conversationId,
    required this.type,
    required this.title,
    this.avatarUrl,
    this.lastMessagePreview,
    this.lastMessageTime,
    required this.memberCount,
    this.circleId,
    this.circleGroupId,
    this.highlightText,
    this.matchedField,
  });

  final String conversationId;
  final String type;
  final String title;
  final String? avatarUrl;
  final String? lastMessagePreview;
  final DateTime? lastMessageTime;
  final int memberCount;
  final String? circleId;
  final String? circleGroupId;
  final String? highlightText;
  final String? matchedField;

  Map<String, Object?> toMap() => <String, Object?>{
    'conversationId': conversationId,
    'type': type,
    'title': title,
    if (avatarUrl != null) 'avatarUrl': avatarUrl,
    if (lastMessagePreview != null) 'lastMessagePreview': lastMessagePreview,
    if (lastMessageTime != null)
      'lastMessageTime': lastMessageTime!.toUtc().toIso8601String(),
    'memberCount': memberCount,
    if (circleId != null) 'circleId': circleId,
    if (circleGroupId != null) 'circleGroupId': circleGroupId,
    if (highlightText != null) 'highlightText': highlightText,
    if (matchedField != null) 'matchedField': matchedField,
  };
}

class MessageSearchItemView {
  const MessageSearchItemView({
    required this.messageId,
    required this.conversationId,
    this.conversationTitle,
    this.conversationAvatarUrl,
    this.senderPersonaId,
    this.senderDisplayName,
    this.senderAvatarUrl,
    required this.messageType,
    required this.contentPreview,
    this.seq,
    required this.timestamp,
    this.highlightText,
    this.matchedField,
  });

  final String messageId;
  final String conversationId;
  final String? conversationTitle;
  final String? conversationAvatarUrl;
  final String? senderPersonaId;
  final String? senderDisplayName;
  final String? senderAvatarUrl;
  final String messageType;
  final String contentPreview;
  final int? seq;
  final DateTime timestamp;
  final String? highlightText;
  final String? matchedField;

  Map<String, Object?> toMap() => <String, Object?>{
    'messageId': messageId,
    'conversationId': conversationId,
    if (conversationTitle != null) 'conversationTitle': conversationTitle,
    if (conversationAvatarUrl != null)
      'conversationAvatarUrl': conversationAvatarUrl,
    if (senderPersonaId != null) 'senderPersonaId': senderPersonaId,
    if (senderDisplayName != null) 'senderDisplayName': senderDisplayName,
    if (senderAvatarUrl != null) 'senderAvatarUrl': senderAvatarUrl,
    'messageType': messageType,
    'contentPreview': contentPreview,
    if (seq != null) 'seq': seq,
    'timestamp': timestamp.toUtc().toIso8601String(),
    if (highlightText != null) 'highlightText': highlightText,
    if (matchedField != null) 'matchedField': matchedField,
  };
}
