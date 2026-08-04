import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";
import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:quwoquan_app/chat/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ConversationCacheRecord {
  const ConversationCacheRecord({
    required this.id,
    this.type = '',
    this.title = '',
    this.avatarUrl = '',
    this.groupAvatarVersion = 0,
    this.groupAvatarSourceHash,
    this.creatorId = '',
    this.circleId = '',
    this.circleGroupId,
    this.originType = 'direct_init',
    this.maxSeq = 0,
    this.lastSeq = 0,
    this.memberCount = 0,
    this.maxGroupSize = 0,
    this.receiptEnabled = true,
    this.lastMessageId,
    this.lastMessagePreview = '',
    this.lastMessageType = MessageType.text,
    this.lastMessageAt = '',
    this.messageCount = 0,
    this.status = '',
    this.createdAt = '',
    this.updatedAt = '',
    this.settingsUpdatedAt = '',
    this.unreadCount = 0,
    this.mentionUnreadCount = 0,
    this.muted = false,
    this.pinned = false,
    this.membersRosterRevision,
  });

  final String id;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String? groupAvatarSourceHash;
  final String creatorId;
  final String circleId;
  final String? circleGroupId;
  final String originType;
  final int maxSeq;
  final int lastSeq;
  final int memberCount;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String? lastMessageId;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final String lastMessageAt;
  final int messageCount;
  final String status;
  final String createdAt;
  final String updatedAt;
  final String settingsUpdatedAt;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final int? membersRosterRevision;

  factory ConversationCacheRecord.fromConversationViewData(
    ConversationViewData dto,
  ) {
    return ConversationCacheRecord(
      id: dto.id.trim(),
      type: dto.type.trim(),
      title: dto.title?.trim() ?? '',
      avatarUrl: dto.avatarUrl?.trim() ?? '',
      groupAvatarVersion: dto.groupAvatarVersion,
      groupAvatarSourceHash: dto.groupAvatarSourceHash?.trim(),
      creatorId: dto.creatorId.trim(),
      circleId: dto.circleId?.trim() ?? '',
      circleGroupId: dto.circleGroupId?.trim(),
      originType: dto.originType.trim().isEmpty
          ? 'direct_init'
          : dto.originType.trim(),
      maxSeq: dto.maxSeq,
      lastSeq: dto.maxSeq,
      memberCount: dto.memberCount,
      maxGroupSize: dto.maxGroupSize,
      receiptEnabled: dto.receiptEnabled,
      lastMessageId: _optionalString(dto.lastMessageId),
      lastMessagePreview: dto.lastMessagePreview?.trim() ?? '',
      lastMessageType: dto.lastMessageType,
      lastMessageAt: dto.lastMessageTime?.toIso8601String() ?? '',
      messageCount: dto.messageCount,
      status: dto.status.trim(),
      createdAt: dto.createdAt.toIso8601String(),
      updatedAt: dto.updatedAt.toIso8601String(),
      settingsUpdatedAt: dto.updatedAt.toIso8601String(),
      membersRosterRevision: dto.membersRosterRevision,
    );
  }

  factory ConversationCacheRecord.fromInboxDto(ChatInboxViewData dto) {
    return ConversationCacheRecord(
      id: dto.id.trim(),
      type: dto.type.trim(),
      title: dto.title.trim(),
      avatarUrl: dto.avatarUrl.trim(),
      groupAvatarVersion: dto.groupAvatarVersion,
      circleId: dto.circleId.trim(),
      lastSeq: dto.lastSeq,
      lastMessagePreview: dto.lastMessagePreview.trim(),
      lastMessageType: dto.lastMessageType,
      lastMessageAt: dto.lastMessageTime?.toIso8601String() ?? '',
      unreadCount: dto.unreadCount,
      mentionUnreadCount: dto.mentionUnreadCount,
      muted: dto.muted,
      pinned: dto.pinned,
    );
  }

  factory ConversationCacheRecord.fromCacheMap(Map<String, Object?> map) {
    return ConversationCacheRecord(
      id: _requiredCacheString(map, 'conversationId'),
      type: _string(map['type']),
      title: _string(map['title']),
      avatarUrl: _string(map['avatarUrl']),
      groupAvatarVersion: _int(map['groupAvatarVersion']),
      groupAvatarSourceHash: _optionalString(map['groupAvatarSourceHash']),
      creatorId: _string(map['creatorId']),
      circleId: _string(map['circleId']),
      circleGroupId: _optionalString(map['circleGroupId']),
      originType: _string(map['originType']),
      maxSeq: _int(map['maxSeq']),
      lastSeq: _int(map['lastSeq']),
      memberCount: _int(map['memberCount']),
      maxGroupSize: _int(map['maxGroupSize']),
      receiptEnabled: _bool(map['receiptEnabled'], fallback: true),
      lastMessageId: _optionalString(map['lastMessageId']),
      lastMessagePreview: _string(map['lastMessagePreview']),
      lastMessageType: map['lastMessageType'] == null
          ? MessageType.text
          : MessageType.fromWire(
              map['lastMessageType'],
              'ConversationCacheRecord.lastMessageType',
            ),
      lastMessageAt: _normalizeIsoString(map['lastMessageAt']) ?? '',
      messageCount: _int(map['messageCount']),
      status: _string(map['status']),
      createdAt: _string(map['createdAt']),
      updatedAt: _string(map['updatedAt']),
      settingsUpdatedAt: _string(map['settingsUpdatedAt']),
      unreadCount: _int(map['unreadCount']),
      mentionUnreadCount: _int(map['mentionUnreadCount']),
      muted: _bool(map['muted']),
      pinned: _bool(map['pinned']),
      membersRosterRevision: _optionalInt(map['membersRosterRevision']),
    );
  }

  String get settingsTimestamp =>
      settingsUpdatedAt.isNotEmpty ? settingsUpdatedAt : updatedAt;

  String get messageTimestamp => lastMessageAt;

  ChatInboxViewData toChatInboxViewData() {
    return ChatInboxViewData(
      id: id,
      type: type,
      title: title,
      avatarUrl: avatarUrl,
      groupAvatarVersion: groupAvatarVersion,
      lastMessagePreview: lastMessagePreview,
      lastMessageType: lastMessageType,
      lastMessageTime: _parseDateTime(lastMessageAt),
      lastSeq: lastSeq > 0 ? lastSeq : maxSeq,
      unreadCount: unreadCount,
      mentionUnreadCount: mentionUnreadCount,
      muted: muted,
      pinned: pinned,
      circleId: circleId,
    );
  }

  ConversationSearchItemView toConversationSearchItemView({
    String? highlightText,
    String? matchedField,
  }) {
    return ConversationSearchItemView(
      conversationId: id,
      type: type.isEmpty ? 'direct' : type,
      title: title.isEmpty ? id : title,
      avatarUrl: avatarUrl.isEmpty ? null : avatarUrl,
      lastMessagePreview: lastMessagePreview.isEmpty
          ? null
          : lastMessagePreview,
      lastMessageTime: _parseDateTime(lastMessageAt),
      memberCount: memberCount,
      circleId: circleId.isEmpty ? null : circleId,
      circleGroupId: circleGroupId,
      highlightText: highlightText,
      matchedField: matchedField,
    );
  }

  ConversationViewData toConversationViewData() {
    return ConversationViewData(
      id: id,
      type: type,
      title: title.isEmpty ? null : title,
      avatarUrl: avatarUrl.isEmpty ? null : avatarUrl,
      groupAvatarVersion: groupAvatarVersion,
      groupAvatarSourceHash: groupAvatarSourceHash,
      creatorId: creatorId,
      circleId: circleId.isEmpty ? null : circleId,
      circleGroupId: circleGroupId,
      originType: originType,
      maxSeq: maxSeq,
      memberCount: memberCount,
      maxGroupSize: maxGroupSize,
      receiptEnabled: receiptEnabled,
      lastMessageId: lastMessageId,
      lastMessagePreview: lastMessagePreview.isEmpty
          ? null
          : lastMessagePreview,
      lastMessageType: lastMessageType,
      lastMessageTime: _parseDateTime(lastMessageAt),
      messageCount: messageCount,
      status: status,
      createdAt: _requiredCacheDateTime(createdAt, 'createdAt'),
      updatedAt: _requiredCacheDateTime(updatedAt, 'updatedAt'),
      membersRosterRevision: membersRosterRevision,
    );
  }

  Map<String, Object?> toCacheMap() {
    return <String, Object?>{
      'conversationId': id,
      if (type.isNotEmpty) 'type': type,
      if (title.isNotEmpty) 'title': title,
      if (avatarUrl.isNotEmpty) 'avatarUrl': avatarUrl,
      'groupAvatarVersion': groupAvatarVersion,
      if (groupAvatarSourceHash != null)
        'groupAvatarSourceHash': groupAvatarSourceHash,
      if (creatorId.isNotEmpty) 'creatorId': creatorId,
      if (circleId.isNotEmpty) 'circleId': circleId,
      if (circleGroupId != null) 'circleGroupId': circleGroupId,
      if (originType.isNotEmpty) 'originType': originType,
      'maxSeq': maxSeq,
      'lastSeq': lastSeq,
      'memberCount': memberCount,
      'maxGroupSize': maxGroupSize,
      'receiptEnabled': receiptEnabled,
      if (lastMessageId != null) 'lastMessageId': lastMessageId,
      if (lastMessagePreview.isNotEmpty)
        'lastMessagePreview': lastMessagePreview,
      'lastMessageType': lastMessageType.wireName,
      if (lastMessageAt.isNotEmpty) 'lastMessageAt': lastMessageAt,
      'messageCount': messageCount,
      if (status.isNotEmpty) 'status': status,
      if (createdAt.isNotEmpty) 'createdAt': createdAt,
      if (updatedAt.isNotEmpty) 'updatedAt': updatedAt,
      if (settingsUpdatedAt.isNotEmpty) 'settingsUpdatedAt': settingsUpdatedAt,
      'unreadCount': unreadCount,
      'mentionUnreadCount': mentionUnreadCount,
      'muted': muted,
      'pinned': pinned,
      if (membersRosterRevision != null)
        'membersRosterRevision': membersRosterRevision,
    };
  }

  ConversationCacheRecord copyWith({
    String? id,
    String? type,
    String? title,
    String? avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
    bool clearGroupAvatarSourceHash = false,
    String? creatorId,
    String? circleId,
    String? circleGroupId,
    bool clearCircleGroupId = false,
    String? originType,
    int? maxSeq,
    int? lastSeq,
    int? memberCount,
    int? maxGroupSize,
    bool? receiptEnabled,
    String? lastMessageId,
    bool clearLastMessageId = false,
    String? lastMessagePreview,
    MessageType? lastMessageType,
    String? lastMessageAt,
    int? messageCount,
    String? status,
    String? createdAt,
    String? updatedAt,
    String? settingsUpdatedAt,
    int? unreadCount,
    int? mentionUnreadCount,
    bool? muted,
    bool? pinned,
    int? membersRosterRevision,
    bool clearMembersRosterRevision = false,
  }) {
    return ConversationCacheRecord(
      id: id ?? this.id,
      type: type ?? this.type,
      title: title ?? this.title,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      groupAvatarVersion: groupAvatarVersion ?? this.groupAvatarVersion,
      groupAvatarSourceHash: clearGroupAvatarSourceHash
          ? null
          : groupAvatarSourceHash ?? this.groupAvatarSourceHash,
      creatorId: creatorId ?? this.creatorId,
      circleId: circleId ?? this.circleId,
      circleGroupId: clearCircleGroupId
          ? null
          : circleGroupId ?? this.circleGroupId,
      originType: originType ?? this.originType,
      maxSeq: maxSeq ?? this.maxSeq,
      lastSeq: lastSeq ?? this.lastSeq,
      memberCount: memberCount ?? this.memberCount,
      maxGroupSize: maxGroupSize ?? this.maxGroupSize,
      receiptEnabled: receiptEnabled ?? this.receiptEnabled,
      lastMessageId: clearLastMessageId
          ? null
          : lastMessageId ?? this.lastMessageId,
      lastMessagePreview: lastMessagePreview ?? this.lastMessagePreview,
      lastMessageType: lastMessageType ?? this.lastMessageType,
      lastMessageAt: lastMessageAt ?? this.lastMessageAt,
      messageCount: messageCount ?? this.messageCount,
      status: status ?? this.status,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      settingsUpdatedAt: settingsUpdatedAt ?? this.settingsUpdatedAt,
      unreadCount: unreadCount ?? this.unreadCount,
      mentionUnreadCount: mentionUnreadCount ?? this.mentionUnreadCount,
      muted: muted ?? this.muted,
      pinned: pinned ?? this.pinned,
      membersRosterRevision: clearMembersRosterRevision
          ? null
          : membersRosterRevision ?? this.membersRosterRevision,
    );
  }
}

class ConversationListPatch {
  const ConversationListPatch({
    this.lastMessagePreview,
    this.lastMessageAt,
    this.unreadCount,
    this.mentionUnreadCount,
  });

  final String? lastMessagePreview;
  final String? lastMessageAt;
  final int? unreadCount;
  final int? mentionUnreadCount;
}

class ConversationAvatarPatch {
  const ConversationAvatarPatch({
    required this.avatarUrl,
    this.groupAvatarVersion,
    this.groupAvatarSourceHash,
  });

  final String avatarUrl;
  final int? groupAvatarVersion;
  final String? groupAvatarSourceHash;
}

DateTime? _parseDateTime(String? value) {
  final normalized = value?.trim() ?? '';
  if (normalized.isEmpty) {
    return null;
  }
  return DateTime.tryParse(normalized);
}

String _requiredCacheString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('ConversationCacheRecord.$key is required');
  }
  return value.trim();
}

DateTime _requiredCacheDateTime(String value, String key) {
  final parsed = _parseDateTime(value);
  if (parsed == null) {
    throw StateError('ConversationCacheRecord.$key is invalid');
  }
  return parsed;
}

String _string(Object? value) => value?.toString().trim() ?? '';

String? _optionalString(Object? value) {
  final text = _string(value);
  return text.isEmpty ? null : text;
}

int _int(Object? value, {int fallback = 0}) {
  return (value as num?)?.toInt() ?? fallback;
}

int? _optionalInt(Object? value) {
  return (value as num?)?.toInt();
}

bool _bool(Object? value, {bool fallback = false}) {
  if (value is bool) {
    return value;
  }
  return fallback;
}

String? _normalizeIsoString(Object? value) {
  if (value is DateTime) {
    return value.toIso8601String();
  }
  if (value is String) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }
  return null;
}
