import 'package:quwoquan_app/notification/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../cloud_services/object_doubles/object_scenario_seed_reader.dart';

/// local_contract Notification 对象替身。
final class AppMessageTypedDouble
    implements AppMessageQuery, AppMessageCommandWriter {
  AppMessageTypedDouble({ObjectScenarioSeedReader? fixtures})
    : _messages = _readMessages(fixtures ?? objectScenarioSeedReader);

  final List<AppMessage> _messages;

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async {
    if (query.limit <= 0 || query.limit > 100) {
      throw ArgumentError.value(
        query.limit,
        'limit',
        'must be between 1 and 100',
      );
    }
    final messageType = query.messageType?.trim() ?? '';
    final matches = _messages
        .where((message) {
          if (messageType.isNotEmpty &&
              message.messageType.wireName != messageType) {
            return false;
          }
          if (query.read != null && message.read != query.read) {
            return false;
          }
          return true;
        })
        .take(query.limit);
    return AppMessageInboxSlice(items: matches.toList(growable: false));
  }

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    final messageId = query.messageId.trim();
    if (messageId.isEmpty) {
      throw ArgumentError.value(query.messageId, 'messageId');
    }
    return _messages.firstWhere((message) => message.messageId == messageId);
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async {
    return AppMessageUnreadCountSlice(
      unreadCount: _messages.where((message) => !message.read).length,
    );
  }

  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) async {
    final message = await getAppMessage(
      GetAppMessageQuery(messageId: command.messageId),
    );
    if (message.ackedAt != null) return message;
    return _replace(message, ackedAt: DateTime.utc(2026, 4, 29, 8, 2));
  }

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) async {
    final message = await getAppMessage(
      GetAppMessageQuery(messageId: command.messageId),
    );
    if (message.read) return message;
    return _replace(
      message,
      read: true,
      readAt: DateTime.utc(2026, 4, 29, 8, 3),
    );
  }

  AppMessage _replace(
    AppMessage current, {
    bool? read,
    DateTime? ackedAt,
    DateTime? readAt,
  }) {
    final replacement = AppMessage(
      messageId: current.messageId,
      userId: current.userId,
      messageType: current.messageType,
      source: current.source,
      sourceId: current.sourceId,
      destination: current.destination,
      title: current.title,
      summary: current.summary,
      target: current.target,
      read: read ?? current.read,
      createdAt: current.createdAt,
      deliveredAt: current.deliveredAt,
      ackedAt: ackedAt ?? current.ackedAt,
      readAt: readAt ?? current.readAt,
    );
    final index = _messages.indexWhere(
      (message) => message.messageId == current.messageId,
    );
    if (index < 0) {
      throw StateError('Notification typed double message is missing');
    }
    _messages[index] = replacement;
    return replacement;
  }

  static List<AppMessage> _readMessages(ObjectScenarioSeedReader fixtures) {
    final decoded = fixtures.document('notification');
    final seedSets = decoded['seedSets'];
    if (seedSets is! Map) {
      throw FormatException('Notification typed double seed seedSets is missing');
    }
    final core = seedSets['notification_core'];
    if (core is! Map || core['appMessages'] is! List) {
      throw FormatException('Notification typed double seed messages are missing');
    }
    return List<AppMessage>.of(
      (core['appMessages'] as List).map(decodeAppMessage),
      growable: true,
    );
  }
}
