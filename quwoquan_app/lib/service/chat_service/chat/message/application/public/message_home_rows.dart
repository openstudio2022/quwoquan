import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

const List<String> messageHomeFilters = <String>[
  'all',
  'unread',
  'group',
  'direct',
  'notification',
];

/// Typed MessageHome result exposed without inbox presentation models.
final class MessageHomeRowsSnapshot {
  const MessageHomeRowsSnapshot({
    required this.rows,
    this.cacheFallbackError,
    this.copyKey,
  });

  final List<MessageHomeRow> rows;
  final Object? cacheFallbackError;
  final String? copyKey;

  bool get isCacheFallback => cacheFallbackError != null;
}

int totalUnreadMessages(Iterable<MessageHomeRow> rows) {
  return rows.fold<int>(0, (total, row) => total + row.unreadCount);
}
