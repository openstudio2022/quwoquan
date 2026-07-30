import '../operation_request_payload.dart';
import 'app_message.dart';
import 'app_message_inbox_slice.dart';
import 'app_message_unread_count_slice.dart';

export 'app_message.dart';
export 'app_message_inbox_slice.dart';
export 'app_message_unread_count_slice.dart';
part '../generated/requests/notification/app_message_contracts.requests.g.dart';

abstract interface class AppMessageQuery {
  Future<AppMessageInboxSlice> listAppMessages(ListAppMessagesQuery query);

  Future<AppMessage> getAppMessage(GetAppMessageQuery query);

  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  );
}

abstract interface class AppMessageCommandWriter {
  Future<AppMessage> acknowledge(AckAppMessageCommand command);

  Future<AppMessage> markRead(ReadAppMessageCommand command);
}

AppMessageInboxSlice decodeAppMessageInboxSlice(Object? response) {
  final root = _expectObject(response, 'App message inbox response');
  _expectOnlyKeys(root, const <String>{'items', 'nextCursor'}, 'inbox');
  final items = root['items'];
  if (items is! List<Object?>) {
    throw const FormatException('App message inbox items must be a list');
  }
  final nextCursor = _optionalString(root['nextCursor'], 'nextCursor');
  return AppMessageInboxSlice(
    items: items.map(decodeAppMessage),
    nextCursor: nextCursor,
  );
}

AppMessage decodeAppMessage(Object? response) {
  final root = _expectObject(response, 'App message response');
  _expectOnlyKeys(root, const <String>{
    'messageId',
    'userId',
    'messageType',
    'source',
    'sourceId',
    'destination',
    'title',
    'summary',
    'target',
    'read',
    'createdAt',
    'deliveredAt',
    'ackedAt',
    'readAt',
  }, 'message');
  final destination = _expectObject(
    root['destination'],
    'App message destination',
  );
  _expectOnlyKeys(destination, const <String>{'type', 'id'}, 'destination');
  final target = _expectObject(root['target'], 'App message target');
  _expectOnlyKeys(target, const <String>{
    'targetType',
    'targetId',
    'routeId',
    'routePath',
    'query',
  }, 'target');
  final routeQuery = _expectObject(target['query'], 'App message target query');
  _expectOnlyKeys(routeQuery, const <String>{'dimension'}, 'target.query');
  return AppMessage(
    messageId: _requiredString(root['messageId'], 'messageId'),
    userId: _requiredString(root['userId'], 'userId'),
    messageType: _requiredString(root['messageType'], 'messageType'),
    source: _requiredString(root['source'], 'source'),
    sourceId: _requiredString(root['sourceId'], 'sourceId'),
    destination: AppMessageDestination(
      type: _requiredString(destination['type'], 'destination.type'),
      id: _requiredString(destination['id'], 'destination.id'),
    ),
    title: _requiredString(root['title'], 'title'),
    summary: _requiredString(root['summary'], 'summary'),
    target: AppMessageTarget(
      targetType: _requiredString(target['targetType'], 'target.targetType'),
      targetId: _requiredString(target['targetId'], 'target.targetId'),
      routeId: _optionalString(target['routeId'], 'target.routeId'),
      routePath: _optionalString(target['routePath'], 'target.routePath'),
      query: AppMessageRouteQuery(
        dimension: _optionalString(
          routeQuery['dimension'],
          'target.query.dimension',
        ),
      ),
    ),
    read: _requiredBool(root['read'], 'read'),
    createdAt: _requiredDateTime(root['createdAt'], 'createdAt'),
    deliveredAt: _optionalDateTime(root['deliveredAt'], 'deliveredAt'),
    ackedAt: _optionalDateTime(root['ackedAt'], 'ackedAt'),
    readAt: _optionalDateTime(root['readAt'], 'readAt'),
  );
}

AppMessageUnreadCountSlice decodeAppMessageUnreadCountSlice(Object? response) {
  final root = _expectObject(response, 'App message unread count response');
  _expectOnlyKeys(root, const <String>{'unreadCount'}, 'unread count');
  final raw = root['unreadCount'];
  if (raw is! num ||
      raw.isNaN ||
      raw.isInfinite ||
      raw != raw.roundToDouble()) {
    throw const FormatException('App message unreadCount must be an integer');
  }
  final unreadCount = raw.toInt();
  if (unreadCount < 0) {
    throw const FormatException('App message unreadCount must not be negative');
  }
  return AppMessageUnreadCountSlice(unreadCount: unreadCount);
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$context must be an object');
  }
  return value;
}

void _expectOnlyKeys(
  Map<Object?, Object?> value,
  Set<String> allowed,
  String context,
) {
  for (final key in value.keys) {
    if (key is! String || !allowed.contains(key)) {
      throw FormatException('$context contains an unknown field');
    }
  }
}

String _requiredString(Object? value, String field) {
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return value.trim();
}

String? _optionalString(Object? value, String field) {
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$field must be a string');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

bool _requiredBool(Object? value, String field) {
  if (value is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return value;
}

DateTime _requiredDateTime(Object? value, String field) {
  final raw = _requiredString(value, field);
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    throw FormatException('$field must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

DateTime? _optionalDateTime(Object? value, String field) {
  if (value == null) return null;
  return _requiredDateTime(value, field);
}
