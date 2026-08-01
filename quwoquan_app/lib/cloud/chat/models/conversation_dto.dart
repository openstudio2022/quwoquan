import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Typed DTO for the Conversation entity.
/// Maps to quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml → Conversation.
class ConversationDto {
  final String id;
  final String type;
  final String? title;
  final String? avatarUrl;
  final int groupAvatarVersion;
  final String? groupAvatarSourceHash;
  final String creatorId;
  final String? circleId;
  final String? circleGroupId;
  final String originType;
  final ChatGreetingIntersectionSnapshot? originIntersectionSnapshot;
  final int maxSeq;
  final int memberCount;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String? lastMessageId;
  final String? lastMessagePreview;
  final MessageType lastMessageType;
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
    this.groupAvatarVersion = 0,
    this.groupAvatarSourceHash,
    required this.creatorId,
    this.circleId,
    this.circleGroupId,
    this.originType = 'direct_init',
    this.originIntersectionSnapshot,
    required this.maxSeq,
    required this.memberCount,
    required this.maxGroupSize,
    required this.receiptEnabled,
    this.lastMessageId,
    this.lastMessagePreview,
    required this.lastMessageType,
    this.lastMessageTime,
    required this.messageCount,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.membersRosterRevision,
  });

  factory ConversationDto.fromMap(Map<String, dynamic> map) {
    return ConversationDto(
      id: _requiredString(map, 'id'),
      type: _requiredString(map, 'type'),
      title: _optionalTypedString(map, 'title'),
      avatarUrl: _optionalString(map['avatarUrl']),
      groupAvatarVersion: (map['groupAvatarVersion'] as num?)?.toInt() ?? 0,
      groupAvatarSourceHash: _optionalString(map['groupAvatarSourceHash']),
      creatorId: _requiredString(map, 'creatorId'),
      circleId: _optionalTypedString(map, 'circleId'),
      circleGroupId: _optionalString(map['circleGroupId']),
      originType: _optionalString(map['originType']) ?? 'direct_init',
      originIntersectionSnapshot: _optionalIntersectionSnapshot(
        map['originIntersectionSnapshot'],
      ),
      maxSeq: (map['maxSeq'] as num?)?.toInt() ?? 0,
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      maxGroupSize: _requiredInt(map, 'maxGroupSize'),
      receiptEnabled: _requiredBool(map, 'receiptEnabled'),
      lastMessageId: _optionalTypedString(map, 'lastMessageId'),
      lastMessagePreview: _optionalTypedString(map, 'lastMessagePreview'),
      lastMessageType: MessageType.fromWire(map['lastMessageType']),
      lastMessageTime: _optionalDateTime(map, 'lastMessageTime'),
      messageCount: (map['messageCount'] as num?)?.toInt() ?? 0,
      status: _requiredString(map, 'status'),
      createdAt: _requiredDateTime(map, 'createdAt'),
      updatedAt: _requiredDateTime(map, 'updatedAt'),
      membersRosterRevision: (map['membersRosterRevision'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toMap() => {
    'id': id,
    'type': type,
    if (title != null) 'title': title,
    if (avatarUrl != null) 'avatarUrl': avatarUrl,
    'groupAvatarVersion': groupAvatarVersion,
    if (groupAvatarSourceHash != null)
      'groupAvatarSourceHash': groupAvatarSourceHash,
    'creatorId': creatorId,
    if (circleId != null) 'circleId': circleId,
    if (circleGroupId != null) 'circleGroupId': circleGroupId,
    'originType': originType,
    if (originIntersectionSnapshot != null)
      'originIntersectionSnapshot': <String, Object?>{
        'intersectionId': originIntersectionSnapshot!.intersectionId,
        'evidenceId': originIntersectionSnapshot!.evidenceId,
        'sourceRef': originIntersectionSnapshot!.sourceRef,
        'objectTypeRef': originIntersectionSnapshot!.objectTypeRef,
        'objectId': originIntersectionSnapshot!.objectId,
        'primaryText': originIntersectionSnapshot!.primaryText,
        if (originIntersectionSnapshot!.dimension != null)
          'dimension': originIntersectionSnapshot!.dimension,
        'resolvedAt': originIntersectionSnapshot!.resolvedAt.toIso8601String(),
      },
    'maxSeq': maxSeq,
    'memberCount': memberCount,
    'maxGroupSize': maxGroupSize,
    'receiptEnabled': receiptEnabled,
    if (lastMessageId != null) 'lastMessageId': lastMessageId,
    if (lastMessagePreview != null) 'lastMessagePreview': lastMessagePreview,
    'lastMessageType': lastMessageType.wireValue,
    if (lastMessageTime != null)
      'lastMessageTime': lastMessageTime!.toIso8601String(),
    'messageCount': messageCount,
    'status': status,
    'createdAt': createdAt.toIso8601String(),
    'updatedAt': updatedAt.toIso8601String(),
    if (membersRosterRevision != null)
      'membersRosterRevision': membersRosterRevision,
  };
}

String? _optionalString(Object? value) {
  final s = value?.toString().trim() ?? '';
  return s.isEmpty ? null : s;
}

String _requiredString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('Conversation.$key must be a non-empty string');
  }
  return value.trim();
}

String? _optionalTypedString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('Conversation.$key must be a string when present');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredInt(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! num) {
    throw FormatException('Conversation.$key must be an integer');
  }
  return value.toInt();
}

bool _requiredBool(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('Conversation.$key must be a boolean');
  }
  return value;
}

DateTime _requiredDateTime(Map<String, dynamic> map, String key) {
  final parsed = _parseDateTime(map[key]);
  if (parsed == null) {
    throw FormatException('Conversation.$key must be an RFC3339 timestamp');
  }
  return parsed;
}

DateTime? _optionalDateTime(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value == null) {
    return null;
  }
  final parsed = _parseDateTime(value);
  if (parsed == null) {
    throw FormatException(
      'Conversation.$key must be an RFC3339 timestamp when present',
    );
  }
  return parsed;
}

DateTime? _parseDateTime(Object? value) {
  if (value is DateTime) {
    return value;
  }
  if (value is String) {
    return DateTime.tryParse(value);
  }
  return null;
}

ChatGreetingIntersectionSnapshot? _optionalIntersectionSnapshot(Object? value) {
  if (value == null) return null;
  if (value is! Map) {
    throw const FormatException(
      'Conversation.originIntersectionSnapshot must be an object when present',
    );
  }
  final map = Map<String, dynamic>.from(value);
  return ChatGreetingIntersectionSnapshot(
    intersectionId: _requiredString(map, 'intersectionId'),
    evidenceId: _requiredString(map, 'evidenceId'),
    sourceRef: _requiredString(map, 'sourceRef'),
    objectTypeRef: _requiredString(map, 'objectTypeRef'),
    objectId: _requiredString(map, 'objectId'),
    primaryText: _requiredString(map, 'primaryText'),
    dimension: _optionalTypedString(map, 'dimension'),
    resolvedAt: _requiredDateTime(map, 'resolvedAt'),
  );
}
