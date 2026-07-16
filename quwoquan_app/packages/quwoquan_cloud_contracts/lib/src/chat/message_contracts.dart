import '../operation_request_payload.dart';

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

final class ChatMessageCardCommand {
  ChatMessageCardCommand({
    required String kind,
    required String title,
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
       subtitle = _optionalText(subtitle),
       thumbnailUrl = _optionalText(thumbnailUrl),
       deeplink = _optionalText(deeplink),
       landingUrl = _optionalText(landingUrl),
       shareText = _optionalText(shareText),
       message = _optionalText(message),
       attributes = List<ChatMessageCardAttribute>.unmodifiable(attributes);

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

final class ChatSendMessageCommand {
  ChatSendMessageCommand({
    required String conversationId,
    required String type,
    required this.content,
    required String clientMsgId,
    String? mediaAssetId,
    this.card,
    String? replyToMessageId,
    Iterable<String> mentions = const <String>[],
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    this.personaContextVersion,
  }) : conversationId = _requiredText(conversationId, 'conversationId'),
       type = _messageType(type),
       clientMsgId = _requiredText(clientMsgId, 'clientMsgId'),
       mediaAssetId = _optionalText(mediaAssetId),
       replyToMessageId = _optionalText(replyToMessageId),
       mentions = List<String>.unmodifiable(
         mentions.map((mention) => _requiredText(mention, 'mention')),
       ),
       senderDisplayNameSnapshot = _optionalText(senderDisplayNameSnapshot),
       senderAvatarUrlSnapshot = _optionalText(senderAvatarUrlSnapshot) {
    final mediaType = const <String>{'audio', 'image', 'video', 'file'};
    if (mediaType.contains(type) && this.mediaAssetId == null) {
      throw ArgumentError('$type message requires mediaAssetId');
    }
    if (!mediaType.contains(type) && this.mediaAssetId != null) {
      throw ArgumentError('$type message must not bind mediaAssetId');
    }
    if (type == 'card' && card == null) {
      throw ArgumentError('card message requires card');
    }
    if (type != 'card' && card != null) {
      throw ArgumentError('$type message must not contain card');
    }
    if (content.runes.length > 5000) {
      throw ArgumentError.value(
        content,
        'content',
        'must not exceed 5000 code points',
      );
    }
    if (type == 'text' && content.trim().isEmpty) {
      throw ArgumentError.value(
        content,
        'content',
        'text message content is required',
      );
    }
    final resolvedCard = card;
    if (resolvedCard != null) {
      if (resolvedCard.title.runes.length > 120) {
        throw ArgumentError.value(
          resolvedCard.title,
          'card.title',
          'must not exceed 120 code points',
        );
      }
      if (resolvedCard.attributes.length > 16) {
        throw ArgumentError.value(
          resolvedCard.attributes.length,
          'card.attributes',
          'must not exceed 16 items',
        );
      }
      final names = <String>{};
      for (final attribute in resolvedCard.attributes) {
        if (!names.add(attribute.name)) {
          throw ArgumentError.value(
            attribute.name,
            'card.attributes',
            'names must be unique',
          );
        }
      }
    }
    if (personaContextVersion != null && personaContextVersion! <= 0) {
      throw ArgumentError.value(
        personaContextVersion,
        'personaContextVersion',
        'must be > 0',
      );
    }
  }

  final String conversationId;
  final String type;
  final String content;
  final String clientMsgId;
  final String? mediaAssetId;
  final ChatMessageCardCommand? card;
  final String? replyToMessageId;
  final List<String> mentions;
  final String? senderDisplayNameSnapshot;
  final String? senderAvatarUrlSnapshot;
  final int? personaContextVersion;
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

CloudOperationRequestPayload encodeChatSendMessageCommand(
  ChatSendMessageCommand command,
) {
  final card = command.card;
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{
      'type': command.type,
      'content': command.content,
      'clientMsgId': command.clientMsgId,
      if (command.mediaAssetId case final value?) 'mediaAssetId': value,
      if (card != null)
        'card': <String, Object?>{
          'kind': card.kind,
          'title': card.title,
          if (card.subtitle case final value?) 'subtitle': value,
          if (card.thumbnailUrl case final value?) 'thumbnailUrl': value,
          if (card.deeplink case final value?) 'deeplink': value,
          if (card.landingUrl case final value?) 'landingUrl': value,
          if (card.shareText case final value?) 'shareText': value,
          if (card.message case final value?) 'message': value,
          'attributes': <Map<String, String>>[
            for (final attribute in card.attributes)
              <String, String>{
                'name': attribute.name,
                'value': attribute.value,
              },
          ],
        },
      if (command.replyToMessageId case final value?) 'replyToMessageId': value,
      if (command.mentions.isNotEmpty) 'mentions': command.mentions,
      if (command.senderDisplayNameSnapshot case final value?)
        'senderDisplayNameSnapshot': value,
      if (command.senderAvatarUrlSnapshot case final value?)
        'senderAvatarUrlSnapshot': value,
      if (command.personaContextVersion case final value?)
        'personaContextVersion': value,
    },
  );
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

String _messageType(String value) {
  final type = _requiredText(value, 'type');
  if (!const <String>{
    'text',
    'audio',
    'image',
    'video',
    'file',
    'card',
  }.contains(type)) {
    throw ArgumentError.value(value, 'type', 'unsupported message type');
  }
  return type;
}

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

String? _optionalText(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
