import '../operation_request_payload.dart';
import 'conversation_contracts.dart' show ChatCommandAck;

export 'conversation_contracts.dart' show ChatCommandAck;
part '../generated/requests/chat/message_contracts.requests.g.dart';

final class ChatMessageCardAttribute {
  ChatMessageCardAttribute({required String name, required String value})
    : name = _requiredText(name, 'attribute.name'),
      value = _requiredText(value, 'attribute.value') {
    if (this.name.runes.length > 64) {
      throw ArgumentError.value(
        this.name,
        'attribute.name',
        'must not exceed 64 code points',
      );
    }
    if (this.value.runes.length > 256) {
      throw ArgumentError.value(
        this.value,
        'attribute.value',
        'must not exceed 256 code points',
      );
    }
  }

  final String name;
  final String value;
}

final class ChatMessageCardObjectRef {
  ChatMessageCardObjectRef({
    required String objectTypeRef,
    required String objectId,
    required String routeId,
  }) : objectTypeRef = _requiredText(objectTypeRef, 'objectRef.objectTypeRef'),
       objectId = _requiredText(objectId, 'objectRef.objectId'),
       routeId = _requiredText(routeId, 'objectRef.routeId');

  final String objectTypeRef;
  final String objectId;
  final String routeId;

  Map<String, Object?> toWire() => <String, Object?>{
    'objectTypeRef': objectTypeRef,
    'objectId': objectId,
    'routeId': routeId,
  };
}

final class ChatMessageCardCommand {
  ChatMessageCardCommand({
    required String kind,
    required String title,
    ChatMessageCardObjectRef? objectRef,
    String? subtitle,
    String? thumbnailUrl,
    String? deeplink,
    String? landingUrl,
    String? shareText,
    String? message,
    Iterable<ChatMessageCardAttribute> attributes =
        const <ChatMessageCardAttribute>[],
  }) : kind = _requiredText(kind, 'card.kind'),
       title = _requiredText(title, 'card.title'),
       objectRef = objectRef,
       subtitle = _optionalText(subtitle),
       thumbnailUrl = _optionalText(thumbnailUrl),
       deeplink = _optionalText(deeplink),
       landingUrl = _optionalText(landingUrl),
       shareText = _optionalText(shareText),
       message = _optionalText(message),
       attributes = List<ChatMessageCardAttribute>.unmodifiable(attributes) {
    _validateMessageCardObjectRef(this.kind, this.objectRef);
  }

  final String kind;
  final String title;
  final ChatMessageCardObjectRef? objectRef;
  final String? subtitle;
  final String? thumbnailUrl;
  final String? deeplink;
  final String? landingUrl;
  final String? shareText;
  final String? message;
  final List<ChatMessageCardAttribute> attributes;
}

void _validateMessageCardObjectRef(
  String kind,
  ChatMessageCardObjectRef? objectRef,
) {
  const actionable = <String, (String, String)>{
    'content_post': ('post', 'contentDetail'),
    'user_profile': ('user', 'userProfile'),
    'entity_profile': ('homepage', 'homepageDetail'),
    'circle': ('circle', 'circleDetail'),
    'gathering': ('gathering', 'gatheringDetail'),
  };
  const nonActionable = <String>{'profile_qr', 'rtc_call_log'};
  final expected = actionable[kind];
  if (expected == null && !nonActionable.contains(kind)) {
    throw ArgumentError.value(kind, 'card.kind', 'is not canonical');
  }
  if (expected == null) {
    if (objectRef != null) {
      throw ArgumentError.value(
        objectRef,
        'card.objectRef',
        'must be absent for non-actionable cards',
      );
    }
    return;
  }
  if (objectRef == null ||
      objectRef.objectTypeRef != expected.$1 ||
      objectRef.routeId != expected.$2) {
    throw ArgumentError.value(
      objectRef,
      'card.objectRef',
      'must match the canonical object type and route for $kind',
    );
  }
}

final class ChatSendMessageResult {
  const ChatSendMessageResult({
    required this.messageId,
    required this.seq,
    required this.timestamp,
  });

  final String messageId;
  final int seq;
  final DateTime timestamp;
}

abstract interface class ChatMessageCommandWriter {
  Future<ChatSendMessageResult> sendMessage(ChatSendMessageCommand command);
}

abstract interface class ChatMessageQuery {
  Future<ChatMessagePageSlice> listMessages(ChatListMessagesQuery query);

  Future<ChatMessageSyncSlice> syncMessages(ChatSyncMessagesQuery query);
}

abstract interface class ChatMessageMutationWriter {
  Future<ChatCommandAck> recallMessage(
    ChatRecallMessageCommand command, {
    required String idempotencyKey,
  });
}

ChatSendMessageResult decodeChatSendMessageResult(Object? response) {
  final root = _expectObject(response, 'SendMessage response');
  _expectOnlyKeys(root, const <String>{
    'messageId',
    'seq',
    'timestamp',
  }, 'SendMessage response');
  final messageId = _requiredResponseText(root['messageId'], 'messageId');
  final seq = root['seq'];
  if (seq is! num || seq.toInt() <= 0 || seq.toDouble() != seq.toInt()) {
    throw const FormatException('SendMessage seq must be a positive integer');
  }
  final timestampText = _requiredResponseText(root['timestamp'], 'timestamp');
  final timestamp = DateTime.tryParse(timestampText);
  if (timestamp == null) {
    throw const FormatException('SendMessage timestamp must be ISO-8601');
  }
  return ChatSendMessageResult(
    messageId: messageId,
    seq: seq.toInt(),
    timestamp: timestamp,
  );
}

final class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    required this.senderName,
    required this.senderAvatar,
    required this.type,
    required this.content,
    required this.mediaAssetId,
    required this.card,
    required this.replyToMessageId,
    required this.mentions,
    required this.status,
    required this.timestamp,
    required this.recalledAt,
    required this.mediaDeliveryUrl,
    required this.mediaType,
    required this.mediaContentType,
    required this.mediaFileSizeBytes,
  });

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String? senderName;
  final String? senderAvatar;
  final String type;
  final String? content;
  final String? mediaAssetId;
  final ChatMessageCard? card;
  final String? replyToMessageId;
  final List<String> mentions;
  final String status;
  final DateTime timestamp;
  final DateTime? recalledAt;
  final String? mediaDeliveryUrl;
  final String? mediaType;
  final String? mediaContentType;
  final int? mediaFileSizeBytes;
}

final class ChatMessageCard {
  const ChatMessageCard({
    required this.kind,
    required this.title,
    required this.subtitle,
    required this.thumbnailUrl,
    required this.deeplink,
    required this.landingUrl,
    required this.shareText,
    required this.message,
    required this.attributes,
  });

  final String kind;
  final String title;
  final String? subtitle;
  final String? thumbnailUrl;
  final String? deeplink;
  final String? landingUrl;
  final String? shareText;
  final String? message;
  final List<ChatMessageCardAttribute> attributes;
}

final class ChatMessagePageSlice {
  const ChatMessagePageSlice({required this.items, this.nextBeforeSeq});

  final List<ChatMessage> items;
  final int? nextBeforeSeq;
}

ChatMessagePageSlice decodeChatMessagePageSlice(Object? response) {
  final root = _expectObject(response, 'ListMessages response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextBeforeSeq',
  }, 'ListMessages response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException('ListMessages response.items must be a list');
  }
  return ChatMessagePageSlice(
    items: List<ChatMessage>.unmodifiable(
      rawItems.map((item) => _decodeChatMessage(item)),
    ),
    nextBeforeSeq: _optionalPositiveInt(root['nextBeforeSeq'], 'nextBeforeSeq'),
  );
}

final class ChatMessageSyncSlice {
  const ChatMessageSyncSlice({required this.messages, required this.hasMore});

  final List<ChatMessage> messages;
  final bool hasMore;
}

ChatMessageSyncSlice decodeChatMessageSyncSlice(Object? response) {
  final root = _expectObject(response, 'SyncMessages response');
  _expectOnlyKeys(root, const <String>{
    'messages',
    'hasMore',
  }, 'SyncMessages response');
  final rawMessages = root['messages'];
  if (rawMessages is! List) {
    throw const FormatException(
      'SyncMessages response.messages must be a list',
    );
  }
  final hasMore = root['hasMore'];
  if (hasMore is! bool) {
    throw const FormatException(
      'SyncMessages response.hasMore must be boolean',
    );
  }
  return ChatMessageSyncSlice(
    messages: List<ChatMessage>.unmodifiable(
      rawMessages.map((item) => _decodeChatMessage(item)),
    ),
    hasMore: hasMore,
  );
}

ChatMessage _decodeChatMessage(Object? value) {
  final item = _expectObject(value, 'Chat message');
  _expectOnlyKeys(item, _messageWireKeys, 'Chat message');
  final rawMentions = item['mentions'];
  if (rawMentions != null &&
      (rawMentions is! List ||
          rawMentions.any((mention) => mention is! String))) {
    throw const FormatException(
      'Chat message mentions must be a list of strings',
    );
  }
  final mentions = rawMentions is List
      ? List<String>.unmodifiable(rawMentions.cast<String>())
      : const <String>[];
  return ChatMessage(
    id: _requiredResponseText(item['id'], 'id'),
    conversationId: _requiredResponseText(
      item['conversationId'],
      'conversationId',
    ),
    seq: _requiredPositiveInt(item['seq'], 'seq'),
    clientMsgId: _requiredResponseText(item['clientMsgId'], 'clientMsgId'),
    senderId: _requiredResponseText(item['senderId'], 'senderId'),
    senderName: _optionalResponseText(item['senderName'], 'senderName'),
    senderAvatar: _optionalResponseText(item['senderAvatar'], 'senderAvatar'),
    type: _requiredResponseText(item['type'], 'type'),
    content: _optionalResponseText(item['content'], 'content'),
    mediaAssetId: _optionalResponseText(item['mediaAssetId'], 'mediaAssetId'),
    card: _decodeChatMessageCard(item['card']),
    replyToMessageId: _optionalResponseText(
      item['replyToMessageId'],
      'replyToMessageId',
    ),
    mentions: mentions,
    status: _requiredResponseText(item['status'], 'status'),
    timestamp: _requiredResponseTimestamp(item['timestamp'], 'timestamp'),
    recalledAt: _optionalResponseTimestamp(item['recalledAt'], 'recalledAt'),
    mediaDeliveryUrl: _optionalResponseText(
      item['mediaDeliveryUrl'],
      'mediaDeliveryUrl',
    ),
    mediaType: _optionalResponseText(item['mediaType'], 'mediaType'),
    mediaContentType: _optionalResponseText(
      item['mediaContentType'],
      'mediaContentType',
    ),
    mediaFileSizeBytes: _optionalPositiveInt(
      item['mediaFileSizeBytes'],
      'mediaFileSizeBytes',
    ),
  );
}

ChatMessageCard? _decodeChatMessageCard(Object? value) {
  if (value == null) {
    return null;
  }
  final card = _expectObject(value, 'Chat message card');
  _expectOnlyKeys(card, _messageCardWireKeys, 'Chat message card');
  final rawAttributes = card['attributes'];
  if (rawAttributes is! List) {
    throw const FormatException('Chat message card attributes must be a list');
  }
  return ChatMessageCard(
    kind: _requiredResponseText(card['kind'], 'card.kind'),
    title: _requiredResponseText(card['title'], 'card.title'),
    subtitle: _optionalResponseText(card['subtitle'], 'card.subtitle'),
    thumbnailUrl: _optionalResponseText(
      card['thumbnailUrl'],
      'card.thumbnailUrl',
    ),
    deeplink: _optionalResponseText(card['deeplink'], 'card.deeplink'),
    landingUrl: _optionalResponseText(card['landingUrl'], 'card.landingUrl'),
    shareText: _optionalResponseText(card['shareText'], 'card.shareText'),
    message: _optionalResponseText(card['message'], 'card.message'),
    attributes: List<ChatMessageCardAttribute>.unmodifiable(
      rawAttributes.map((attribute) {
        final item = _expectObject(attribute, 'Chat message card attribute');
        _expectOnlyKeys(item, const <String>{
          'name',
          'value',
        }, 'Chat message card attribute');
        return ChatMessageCardAttribute(
          name: _requiredResponseText(item['name'], 'attribute.name'),
          value: _requiredResponseText(item['value'], 'attribute.value'),
        );
      }),
    ),
  );
}

const Set<String> _messageWireKeys = <String>{
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
  'card',
  'replyToMessageId',
  'mentions',
  'status',
  'timestamp',
  'recalledAt',
  'mediaDeliveryUrl',
  'mediaType',
  'mediaContentType',
  'mediaFileSizeBytes',
};

const Set<String> _messageCardWireKeys = <String>{
  'kind',
  'title',
  'subtitle',
  'thumbnailUrl',
  'deeplink',
  'landingUrl',
  'shareText',
  'message',
  'attributes',
};

Map<String, Object?> _expectObject(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map<String, Object?>(
    (key, item) => MapEntry(key.toString(), item),
  );
}

void _expectOnlyKeys(
  Map<String, Object?> value,
  Set<String> allowed,
  String context,
) {
  final unexpected = value.keys.where((key) => !allowed.contains(key)).toList();
  if (unexpected.isNotEmpty) {
    throw FormatException('$context contains unexpected keys: $unexpected');
  }
}

String _requiredText(Object? value, String field) {
  if (value is! String || value.trim().isEmpty) {
    throw ArgumentError.value(value, field, 'must be a non-empty string');
  }
  return value.trim();
}

String _requiredResponseText(Object? value, String field) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('SendMessage $field must be a non-empty string');
  }
  return value.trim();
}

String? _optionalResponseText(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String) {
    throw FormatException('$field must be a string when present');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredPositiveInt(Object? value, String field) {
  if (value is! num ||
      value.toInt() <= 0 ||
      value.toDouble() != value.toInt()) {
    throw FormatException('$field must be a positive integer');
  }
  return value.toInt();
}

int? _optionalPositiveInt(Object? value, String field) {
  if (value == null) {
    return null;
  }
  return _requiredPositiveInt(value, field);
}

DateTime _requiredResponseTimestamp(Object? value, String field) {
  final text = _requiredResponseText(value, field);
  final timestamp = DateTime.tryParse(text);
  if (timestamp == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return timestamp.toUtc();
}

DateTime? _optionalResponseTimestamp(Object? value, String field) {
  if (value == null) {
    return null;
  }
  return _requiredResponseTimestamp(value, field);
}

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
