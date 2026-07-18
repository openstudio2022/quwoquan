import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';

class LocalChatSearchMessageRecord {
  static const int schema = 1;

  const LocalChatSearchMessageRecord({
    required this.messageId,
    required this.conversationId,
    this.conversationType = '',
    this.conversationTitle = '',
    this.conversationAvatarUrl = '',
    this.senderPersonaId = '',
    this.senderDisplayName = '',
    this.senderAvatarUrl = '',
    this.messageType = 'text',
    this.contentPreview = '',
    this.seq = 0,
    this.timestamp = '',
    this.status = 'sent',
    this.recalledAt = '',
    this.deleted = false,
    this.highlightText,
    this.matchedField,
  });

  final String messageId;
  final String conversationId;
  final String conversationType;
  final String conversationTitle;
  final String conversationAvatarUrl;
  final String senderPersonaId;
  final String senderDisplayName;
  final String senderAvatarUrl;
  final String messageType;
  final String contentPreview;
  final int seq;
  final String timestamp;
  final String status;
  final String recalledAt;
  final bool deleted;
  final String? highlightText;
  final String? matchedField;

  factory LocalChatSearchMessageRecord.fromMessageDto(
    MessageDto dto, {
    ConversationCacheRecord? conversation,
  }) {
    final conversationId = dto.conversationId.trim();
    return LocalChatSearchMessageRecord(
      messageId: dto.id.trim(),
      conversationId: conversationId,
      conversationType: conversation?.type ?? '',
      conversationTitle: conversation?.title ?? '',
      conversationAvatarUrl: conversation?.avatarUrl ?? '',
      senderPersonaId: dto.senderId.trim(),
      senderDisplayName: dto.senderName?.trim() ?? '',
      senderAvatarUrl: dto.senderAvatar?.trim() ?? '',
      messageType: dto.type.trim().isEmpty ? 'text' : dto.type.trim(),
      contentPreview: dto.content?.trim() ?? '',
      seq: dto.seq,
      timestamp: dto.timestamp?.toIso8601String() ?? '',
      status: dto.status.trim().isEmpty ? 'sent' : dto.status.trim(),
      recalledAt: dto.recalledAt?.toIso8601String() ?? '',
      deleted:
          dto.recalledAt != null ||
          dto.status == 'recalled' ||
          dto.status == 'deleted',
    );
  }

  factory LocalChatSearchMessageRecord.fromProjectionMap(
    Map<String, dynamic> map, {
    ConversationCacheRecord? conversation,
  }) {
    const allowedKeys = <String>{
      'schema',
      'messageId',
      'conversationId',
      'conversationType',
      'conversationTitle',
      'conversationAvatarUrl',
      'senderPersonaId',
      'senderDisplayName',
      'senderAvatarUrl',
      'messageType',
      'contentPreview',
      'seq',
      'timestamp',
      'status',
      'recalledAt',
      'deleted',
      'highlightText',
      'matchedField',
    };
    final unknownKeys = map.keys.toSet().difference(allowedKeys);
    if (unknownKeys.isNotEmpty) {
      throw FormatException(
        'LocalChatSearchMessageRecord contains unknown fields: '
        '${unknownKeys.toList()..sort()}',
      );
    }
    final version = map['schema'];
    if (version != schema) {
      throw FormatException(
        'Unsupported LocalChatSearchMessageRecord schema: $version',
      );
    }
    return LocalChatSearchMessageRecord(
      messageId: _requiredProjectionString(map, 'messageId'),
      conversationId: _requiredProjectionString(map, 'conversationId'),
      conversationType: _projectionString(map, 'conversationType'),
      conversationTitle: _firstNonEmpty(<Object?>[
        map['conversationTitle'],
        conversation?.title,
      ]),
      conversationAvatarUrl: _firstNonEmpty(<Object?>[
        map['conversationAvatarUrl'],
        conversation?.avatarUrl,
      ]),
      senderPersonaId: _projectionString(map, 'senderPersonaId'),
      senderDisplayName: _projectionString(map, 'senderDisplayName'),
      senderAvatarUrl: _projectionString(map, 'senderAvatarUrl'),
      messageType: _requiredProjectionString(map, 'messageType'),
      contentPreview: _projectionString(map, 'contentPreview'),
      seq: _requiredProjectionInt(map, 'seq'),
      timestamp: _requiredProjectionString(map, 'timestamp'),
      status: _requiredProjectionString(map, 'status'),
      recalledAt: _projectionString(map, 'recalledAt'),
      deleted: _requiredProjectionBool(map, 'deleted'),
      matchedField: _nullableProjectionString(map, 'matchedField'),
      highlightText: _nullableProjectionString(map, 'highlightText'),
    );
  }

  MessageSearchItemView toMessageSearchItemView() {
    return MessageSearchItemView(
      messageId: messageId,
      conversationId: conversationId,
      conversationTitle: conversationTitle.isEmpty ? null : conversationTitle,
      conversationAvatarUrl: conversationAvatarUrl.isEmpty
          ? null
          : conversationAvatarUrl,
      senderPersonaId: senderPersonaId.isEmpty ? null : senderPersonaId,
      senderDisplayName: senderDisplayName.isEmpty ? null : senderDisplayName,
      senderAvatarUrl: senderAvatarUrl.isEmpty ? null : senderAvatarUrl,
      messageType: messageType,
      contentPreview: contentPreview,
      seq: seq > 0 ? seq : null,
      timestamp: _parseTimestamp(timestamp),
      highlightText: highlightText,
      matchedField: matchedField,
    );
  }

  LocalChatSearchMessageRecord copyWith({
    String? messageId,
    String? conversationId,
    String? conversationType,
    String? conversationTitle,
    String? conversationAvatarUrl,
    String? senderPersonaId,
    String? senderDisplayName,
    String? senderAvatarUrl,
    String? messageType,
    String? contentPreview,
    int? seq,
    String? timestamp,
    String? status,
    String? recalledAt,
    bool? deleted,
    String? highlightText,
    String? matchedField,
  }) {
    return LocalChatSearchMessageRecord(
      messageId: messageId ?? this.messageId,
      conversationId: conversationId ?? this.conversationId,
      conversationType: conversationType ?? this.conversationType,
      conversationTitle: conversationTitle ?? this.conversationTitle,
      conversationAvatarUrl:
          conversationAvatarUrl ?? this.conversationAvatarUrl,
      senderPersonaId: senderPersonaId ?? this.senderPersonaId,
      senderDisplayName: senderDisplayName ?? this.senderDisplayName,
      senderAvatarUrl: senderAvatarUrl ?? this.senderAvatarUrl,
      messageType: messageType ?? this.messageType,
      contentPreview: contentPreview ?? this.contentPreview,
      seq: seq ?? this.seq,
      timestamp: timestamp ?? this.timestamp,
      status: status ?? this.status,
      recalledAt: recalledAt ?? this.recalledAt,
      deleted: deleted ?? this.deleted,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }

  Map<String, dynamic> toProjectionMap() {
    return <String, dynamic>{
      'schema': schema,
      'messageId': messageId,
      'conversationId': conversationId,
      'conversationType': conversationType,
      'conversationTitle': conversationTitle,
      'conversationAvatarUrl': conversationAvatarUrl,
      'senderPersonaId': senderPersonaId,
      'senderDisplayName': senderDisplayName,
      'senderAvatarUrl': senderAvatarUrl,
      'messageType': messageType,
      'contentPreview': contentPreview,
      'seq': seq,
      'timestamp': timestamp,
      'status': status,
      'recalledAt': recalledAt,
      'deleted': deleted,
      if (highlightText != null) 'highlightText': highlightText,
      if (matchedField != null) 'matchedField': matchedField,
    };
  }
}

String _requiredProjectionString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty String');
  }
  return value.trim();
}

String _projectionString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value == null) return '';
  if (value is! String) {
    throw FormatException('$key must be a String');
  }
  return value.trim();
}

String? _nullableProjectionString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$key must be a String');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredProjectionInt(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! int) {
    throw FormatException('$key must be an int');
  }
  return value;
}

bool _requiredProjectionBool(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('$key must be a bool');
  }
  return value;
}

String _firstNonEmpty(List<Object?> values) {
  for (final value in values) {
    final text = value?.toString().trim() ?? '';
    if (text.isNotEmpty) {
      return text;
    }
  }
  return '';
}

DateTime _parseTimestamp(String value) {
  return DateTime.tryParse(value.trim()) ?? DateTime.now();
}
