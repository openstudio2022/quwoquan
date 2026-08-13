import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'app_message_test_builder.dart';

/// 无站内信的 Notification 对象替身。
///
/// 给「只是被未读角标 transitively 拉起 notification 对象」的页面套件用：它们的被测
/// 行为与站内信内容无关，只需要 `appMessageQueryProvider` 有一个真实 typed 实现，
/// 从而不会掉进 generated client。不读任何场景种子，避免与被测行为无关的数据漂移
/// 把页面测试弄红。需要真实站内信语义时用 [AppMessageTypedDouble]。
final class EmptyAppMessageQueryDouble implements AppMessageQuery {
  const EmptyAppMessageQueryDouble();

  @override
  Future<AppMessageInboxSlice> listAppMessages(
    ListAppMessagesQuery query,
  ) async => const AppMessageInboxSlice(items: <AppMessage>[]);

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) async {
    throw StateError('EmptyAppMessageQueryDouble 不承载站内信；本套件不应读取单条 AppMessage');
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) async => const AppMessageUnreadCountSlice(unreadCount: 0);
}

/// local_contract Notification 对象替身。
final class AppMessageTypedDouble
    implements AppMessageQuery, AppMessageCommandWriter {
  AppMessageTypedDouble({List<AppMessage>? messages})
    : _messages = List<AppMessage>.of(messages ?? _defaultMessages);

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

  static final List<AppMessage> _defaultMessages = appMessageWireExamples()
      .map(decodeAppMessage)
      .toList(growable: false);
}
