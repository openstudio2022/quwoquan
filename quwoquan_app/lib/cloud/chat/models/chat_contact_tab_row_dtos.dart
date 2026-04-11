/// 联系人 Tab「圈子」占位行（无独立云 metadata 路由时仍强类型出口）。
class ChatContactTabCircleRowDto {
  const ChatContactTabCircleRowDto({
    required this.circleId,
    required this.displayName,
    required this.avatarUrl,
    this.subtitle = '',
  });

  final String circleId;
  final String displayName;
  final String avatarUrl;
  final String subtitle;

  factory ChatContactTabCircleRowDto.fromMap(Map<String, dynamic> m) {
    final id = (m['circleId'] ?? m['id'] ?? '').toString();
    return ChatContactTabCircleRowDto(
      circleId: id,
      displayName: (m['displayName'] ?? '').toString(),
      avatarUrl: (m['avatarUrl'] ?? '').toString(),
      subtitle: (m['subtitle'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'circleId': circleId,
        'id': circleId,
        'displayName': displayName,
        'avatarUrl': avatarUrl,
        'subtitle': subtitle,
      };
}

/// 联系人 Tab「趣群」占位行。
class ChatContactTabFunGroupRowDto {
  const ChatContactTabFunGroupRowDto({
    required this.conversationId,
    required this.displayName,
    required this.avatarUrl,
    this.subtitle = '',
  });

  final String conversationId;
  final String displayName;
  final String avatarUrl;
  final String subtitle;

  factory ChatContactTabFunGroupRowDto.fromMap(Map<String, dynamic> m) {
    final id = (m['conversationId'] ?? m['id'] ?? '').toString();
    return ChatContactTabFunGroupRowDto(
      conversationId: id,
      displayName: (m['displayName'] ?? '').toString(),
      avatarUrl: (m['avatarUrl'] ?? '').toString(),
      subtitle: (m['subtitle'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'conversationId': conversationId,
        'id': conversationId,
        'displayName': displayName,
        'avatarUrl': avatarUrl,
        'subtitle': subtitle,
      };
}
