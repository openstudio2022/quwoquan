import '../operation_request_payload.dart';
part '../generated/requests/chat/message_home_contracts.requests.g.dart';

abstract interface class ChatMessageHomeQuery {
  Future<ChatMessageHomePageSlice> listMessageHome(
    ChatListMessageHomeQuery query,
  );
}





final class ChatMessageHomeItem {
  const ChatMessageHomeItem({
    required this.id,
    required this.kind,
    required this.conversationId,
    required this.notificationId,
    required this.conversationType,
    required this.title,
    required this.summary,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.lastActiveAt,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.muted,
    required this.pinned,
    required this.notificationType,
    required this.read,
  });

  final String id;
  final String kind;
  final String conversationId;
  final String notificationId;
  final String conversationType;
  final String title;
  final String summary;
  final String avatarUrl;
  final int groupAvatarVersion;
  final DateTime? lastActiveAt;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String notificationType;
  final bool read;
}

final class ChatMessageHomePageSlice {
  const ChatMessageHomePageSlice({required this.items, this.nextCursor});

  final List<ChatMessageHomeItem> items;
  final String? nextCursor;
}

ChatMessageHomePageSlice decodeChatMessageHomePageSlice(Object? response) {
  final root = _expectObject(response, 'ListMessageHome response');
  _expectOnlyKeys(root, const <String>{
    'items',
    'nextCursor',
  }, 'ListMessageHome response');
  final rawItems = root['items'];
  if (rawItems is! List) {
    throw const FormatException(
      'ListMessageHome response.items must be a list',
    );
  }
  return ChatMessageHomePageSlice(
    items: List<ChatMessageHomeItem>.unmodifiable(
      rawItems.map(_decodeMessageHomeItem),
    ),
    nextCursor: _optionalNonBlankText(root['nextCursor'], 'nextCursor'),
  );
}

ChatMessageHomeItem _decodeMessageHomeItem(Object? value) {
  final item = _expectObject(value, 'MessageHome item');
  _expectOnlyKeys(item, _messageHomeWireKeys, 'MessageHome item');
  return ChatMessageHomeItem(
    id: _requiredNonBlankText(item['id'], 'id'),
    kind: _requiredNonBlankText(item['kind'], 'kind'),
    conversationId: _requiredString(item['conversationId'], 'conversationId'),
    notificationId: _requiredString(item['notificationId'], 'notificationId'),
    conversationType: _requiredString(
      item['conversationType'],
      'conversationType',
    ),
    title: _requiredString(item['title'], 'title'),
    summary: _requiredString(item['summary'], 'summary'),
    avatarUrl: _requiredString(item['avatarUrl'], 'avatarUrl'),
    groupAvatarVersion: _requiredNonNegativeInt(
      item['groupAvatarVersion'],
      'groupAvatarVersion',
    ),
    lastActiveAt: _optionalTimestamp(item['lastActiveAt'], 'lastActiveAt'),
    unreadCount: _requiredNonNegativeInt(item['unreadCount'], 'unreadCount'),
    mentionUnreadCount: _requiredNonNegativeInt(
      item['mentionUnreadCount'],
      'mentionUnreadCount',
    ),
    muted: _requiredBool(item['muted'], 'muted'),
    pinned: _requiredBool(item['pinned'], 'pinned'),
    notificationType: _requiredString(
      item['notificationType'],
      'notificationType',
    ),
    read: _requiredBool(item['read'], 'read'),
  );
}

Map<String, Object?> _expectObject(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map<String, Object?>((key, item) => MapEntry('$key', item));
}

void _expectOnlyKeys(
  Map<String, Object?> value,
  Set<String> allowed,
  String context,
) {
  final unknown = value.keys
      .where((key) => !allowed.contains(key))
      .toList(growable: false);
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$context contains unknown fields: ${unknown.join(',')}',
    );
  }
}

String _requiredNonBlankText(Object? value, String field) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be a non-blank string');
  }
  return value.trim();
}

String _requiredString(Object? value, String field) {
  if (value is! String) {
    throw FormatException('$field must be a string');
  }
  return value;
}

String? _optionalNonBlankText(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be a non-blank string when present');
  }
  return value.trim();
}

int _requiredNonNegativeInt(Object? value, String field) {
  if (value is! int || value < 0) {
    throw FormatException('$field must be a non-negative integer');
  }
  return value;
}

bool _requiredBool(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return value;
}

DateTime? _optionalTimestamp(Object? value, String field) {
  if (value == null) {
    return null;
  }
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be an RFC3339 timestamp when present');
  }
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$field must be an RFC3339 timestamp when present');
  }
  return parsed.toUtc();
}

const Set<String> _messageHomeWireKeys = <String>{
  'id',
  'kind',
  'conversationId',
  'notificationId',
  'conversationType',
  'title',
  'summary',
  'avatarUrl',
  'groupAvatarVersion',
  'lastActiveAt',
  'unreadCount',
  'mentionUnreadCount',
  'muted',
  'pinned',
  'notificationType',
  'read',
};
