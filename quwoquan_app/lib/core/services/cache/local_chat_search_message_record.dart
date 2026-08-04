import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

class LocalChatSearchMessageRecord {
  static const int schema = 2;

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
    this.messagePayload = const <String, Object?>{},
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

  /// 完整 canonical ChatMessageView 投影；搜索列只负责索引，不得代替时间线事实。
  final Map<String, Object?> messagePayload;
  final String? highlightText;
  final String? matchedField;

  factory LocalChatSearchMessageRecord.fromMessageViewData(
    ChatMessageViewData message, {
    ConversationCacheRecord? conversation,
  }) {
    final conversationId = message.conversationId.trim();
    return LocalChatSearchMessageRecord(
      messageId: message.id.trim(),
      conversationId: conversationId,
      conversationType: conversation?.type ?? '',
      conversationTitle: conversation?.title ?? '',
      conversationAvatarUrl: conversation?.avatarUrl ?? '',
      senderPersonaId: message.senderId.trim(),
      senderDisplayName: message.senderName?.trim() ?? '',
      senderAvatarUrl: message.senderAvatar?.trim() ?? '',
      messageType: message.type.trim().isEmpty ? 'text' : message.type.trim(),
      contentPreview: message.content?.trim() ?? '',
      seq: message.seq,
      timestamp: message.timestamp?.toIso8601String() ?? '',
      status: message.status.trim().isEmpty ? 'sent' : message.status.trim(),
      recalledAt: message.recalledAt?.toIso8601String() ?? '',
      deleted:
          message.recalledAt != null ||
          message.status == 'recalled' ||
          message.status == 'deleted',
      messagePayload: _messageViewDataToStorageMap(message),
    );
  }

  factory LocalChatSearchMessageRecord.fromProjectionMap(
    Map<String, Object?> map, {
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
      'messagePayload',
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
      messagePayload: _projectionMap(map, 'messagePayload'),
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
    Map<String, Object?>? messagePayload,
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
      messagePayload: messagePayload ?? this.messagePayload,
      highlightText: highlightText ?? this.highlightText,
      matchedField: matchedField ?? this.matchedField,
    );
  }

  Map<String, Object?> toProjectionMap() {
    return <String, Object?>{
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
      'messagePayload': messagePayload,
      if (highlightText != null) 'highlightText': highlightText,
      if (matchedField != null) 'matchedField': matchedField,
    };
  }

  ChatMessageViewData toMessageViewData() {
    if (messagePayload.isNotEmpty) {
      return _messageViewDataFromStorageMap(messagePayload);
    }
    return ChatMessageViewData(
      id: messageId,
      conversationId: conversationId,
      seq: seq,
      clientMsgId: messageId,
      senderId: senderPersonaId,
      senderName: senderDisplayName.isEmpty ? null : senderDisplayName,
      senderAvatar: senderAvatarUrl.isEmpty ? null : senderAvatarUrl,
      type: messageType,
      content: contentPreview,
      status: status,
      recalledAt: recalledAt.trim().isEmpty
          ? null
          : DateTime.tryParse(recalledAt.trim()),
      timestamp: timestamp.trim().isEmpty
          ? null
          : DateTime.tryParse(timestamp.trim()),
    );
  }
}

Map<String, Object?> _messageViewDataToStorageMap(ChatMessageViewData message) {
  return <String, Object?>{
    'id': message.id,
    'conversationId': message.conversationId,
    'seq': message.seq,
    'clientMsgId': message.clientMsgId,
    'senderId': message.senderId,
    'senderName': message.senderName,
    'senderAvatar': message.senderAvatar,
    'type': message.type,
    'content': message.content,
    'mediaAssetId': message.mediaAssetId,
    'mediaDeliveryUrl': message.mediaDeliveryUrl,
    'mediaType': message.mediaType,
    'mediaContentType': message.mediaContentType,
    'mediaFileSizeBytes': message.mediaFileSizeBytes,
    'card': message.card?.toWire(),
    'replyToMessageId': message.replyToMessageId,
    'mentions': message.mentions,
    'status': message.status,
    'recalledAt': message.recalledAt?.toIso8601String(),
    'timestamp': message.timestamp?.toIso8601String(),
  };
}

ChatMessageViewData _messageViewDataFromStorageMap(Map<String, Object?> map) {
  const allowed = <String>{
    'id',
    'conversationId',
    'seq',
    'clientMsgId',
    'senderId',
    'senderName',
    'senderAvatar',
    'type',
    'content',
    'mediaAssetId',
    'mediaDeliveryUrl',
    'mediaType',
    'mediaContentType',
    'mediaFileSizeBytes',
    'card',
    'replyToMessageId',
    'mentions',
    'status',
    'recalledAt',
    'timestamp',
  };
  final unknown = map.keys.toSet().difference(allowed);
  if (unknown.isNotEmpty) {
    throw FormatException(
      'Cached chat message contains unknown fields: ${unknown.join(', ')}',
    );
  }
  final mentions = map['mentions'];
  if (mentions != null &&
      (mentions is! List || mentions.any((value) => value is! String))) {
    throw const FormatException('Cached chat message mentions are invalid');
  }
  return ChatMessageViewData(
    id: _requiredStorageString(map, 'id'),
    conversationId: _requiredStorageString(map, 'conversationId'),
    seq: _requiredStorageInt(map, 'seq'),
    clientMsgId: _requiredStorageString(map, 'clientMsgId'),
    senderId: _requiredStorageString(map, 'senderId'),
    senderName: _optionalStorageString(map, 'senderName'),
    senderAvatar: _optionalStorageString(map, 'senderAvatar'),
    type: _requiredStorageString(map, 'type'),
    content: _optionalStorageString(map, 'content'),
    mediaAssetId: _optionalStorageString(map, 'mediaAssetId'),
    mediaDeliveryUrl: _optionalStorageString(map, 'mediaDeliveryUrl'),
    mediaType: _optionalStorageString(map, 'mediaType'),
    mediaContentType: _optionalStorageString(map, 'mediaContentType'),
    mediaFileSizeBytes: _optionalStorageInt(map, 'mediaFileSizeBytes'),
    card: _messageCardFromStorage(map['card']),
    replyToMessageId: _optionalStorageString(map, 'replyToMessageId'),
    mentions: mentions == null
        ? null
        : List<String>.unmodifiable((mentions as List).cast<String>()),
    status: _requiredStorageString(map, 'status'),
    recalledAt: _optionalStorageTimestamp(map, 'recalledAt'),
    timestamp: _optionalStorageTimestamp(map, 'timestamp'),
  );
}

MessageCard? _messageCardFromStorage(Object? value) {
  if (value == null) return null;
  if (value is! Map) {
    throw const FormatException('Cached chat message card must be an object');
  }
  final map = <String, Object?>{
    for (final entry in value.entries)
      if (entry.key is String) entry.key as String: entry.value,
  };
  final attributes = map['attributes'];
  if (attributes is! List) {
    throw const FormatException(
      'Cached chat message card attributes must be a list',
    );
  }
  return MessageCard(
    kind: MessageCardKind.fromWire(map['kind'], 'CachedChatMessage.card.kind'),
    title: _requiredStorageString(map, 'title'),
    objectRef: _messageCardObjectRefFromStorage(map['objectRef']),
    subtitle: _optionalStorageString(map, 'subtitle'),
    thumbnailUrl: _optionalStorageString(map, 'thumbnailUrl'),
    deeplink: _optionalStorageString(map, 'deeplink'),
    landingUrl: _optionalStorageString(map, 'landingUrl'),
    shareText: _optionalStorageString(map, 'shareText'),
    message: _optionalStorageString(map, 'message'),
    attributes: List<MessageCardAttribute>.unmodifiable(
      attributes.map((raw) {
        if (raw is! Map) {
          throw const FormatException(
            'Cached chat message card attribute must be an object',
          );
        }
        final attribute = <String, Object?>{
          for (final entry in raw.entries)
            if (entry.key is String) entry.key as String: entry.value,
        };
        return MessageCardAttribute(
          name: _requiredStorageString(attribute, 'name'),
          value: _requiredStorageString(attribute, 'value'),
        );
      }),
    ),
  );
}

MessageCardObjectRef? _messageCardObjectRefFromStorage(Object? value) {
  if (value == null) return null;
  if (value is! Map) {
    throw const FormatException(
      'Cached chat message card objectRef must be an object',
    );
  }
  final map = <String, Object?>{
    for (final entry in value.entries)
      if (entry.key is String) entry.key as String: entry.value,
  };
  return MessageCardObjectRef(
    objectTypeRef: _requiredStorageString(map, 'objectTypeRef'),
    objectId: _requiredStorageString(map, 'objectId'),
    routeId: _requiredStorageString(map, 'routeId'),
  );
}

String _requiredStorageString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String) {
    throw FormatException('Cached chat message $key must be a String');
  }
  return value;
}

String? _optionalStorageString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('Cached chat message $key must be a String');
  }
  return value;
}

int _requiredStorageInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int) {
    throw FormatException('Cached chat message $key must be an int');
  }
  return value;
}

int? _optionalStorageInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! int) {
    throw FormatException('Cached chat message $key must be an int');
  }
  return value;
}

DateTime? _optionalStorageTimestamp(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('Cached chat message $key must be a timestamp');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('Cached chat message $key must be a timestamp');
  }
  return parsed;
}

Map<String, Object?> _projectionMap(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return const <String, Object?>{};
  if (value is! Map) {
    throw FormatException('$key must be an object');
  }
  return <String, Object?>{
    for (final entry in value.entries)
      if (entry.key is String) entry.key as String: entry.value,
  };
}

String _requiredProjectionString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty String');
  }
  return value.trim();
}

String _projectionString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return '';
  if (value is! String) {
    throw FormatException('$key must be a String');
  }
  return value.trim();
}

String? _nullableProjectionString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$key must be a String');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredProjectionInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int) {
    throw FormatException('$key must be an int');
  }
  return value;
}

bool _requiredProjectionBool(Map<String, Object?> map, String key) {
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
