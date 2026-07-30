import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 消息页`通知`维度唯一数据源：notification-service 云端 AppMessage inbox。
/// 不做本地拼接、不从会话标题猜测（commercial-message-system spec 4.1）。
final notificationInboxProvider = FutureProvider<List<AppMessage>>((ref) async {
  final query = ref.watch(appMessageQueryProvider);
  final slice = await query.listAppMessages(
    ListAppMessagesQuery(limit: 50),
  );
  return slice.items;
});

/// 消息 tab 通知未读徽标唯一数据源：GetAppMessageUnreadCount。
final appMessageUnreadCountProvider = FutureProvider<int>((ref) async {
  final query = ref.watch(appMessageQueryProvider);
  final slice = await query.getUnreadCount(
    GetAppMessageUnreadCountQuery(),
  );
  return slice.unreadCount;
});

/// 点击通知行后推进已读并同步失效 inbox 与未读徽标。
Future<void> markAppMessageReadAndRefresh(
  WidgetRef ref,
  String messageId,
) async {
  final writer = ref.read(appMessageCommandWriterProvider);
  await writer.markRead(ReadAppMessageCommand(messageId: messageId));
  ref.invalidate(notificationInboxProvider);
  ref.invalidate(appMessageUnreadCountProvider);
}
