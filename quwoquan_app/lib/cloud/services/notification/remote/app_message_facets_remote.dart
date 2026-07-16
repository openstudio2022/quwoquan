import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef NotificationInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Notification AppMessage 的 production Remote adapter。
///
/// path、operation、auth、deadline、retry、decoder 与 telemetry 全部由
/// generated client/executor 承担；本层只绑定 typed Facet。
final class RemoteAppMessageAdapter
    implements AppMessageQuery, AppMessageCommandWriter {
  const RemoteAppMessageAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final NotificationInvocationContextFactory invocationContext;

  @override
  Future<AppMessageInboxSlice> listAppMessages(ListAppMessagesQuery query) {
    return client.notificationNotificationListAppMessages(
      query,
      context: invocationContext(NotificationRequestPageIds.listAppMessages),
    );
  }

  @override
  Future<AppMessage> getAppMessage(GetAppMessageQuery query) {
    return client.notificationNotificationGetAppMessage(
      query,
      context: invocationContext(NotificationRequestPageIds.getAppMessage),
    );
  }

  @override
  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  ) {
    return client.notificationNotificationGetAppMessageUnreadCount(
      query,
      context: invocationContext(
        NotificationRequestPageIds.getAppMessageUnreadCount,
      ),
    );
  }

  @override
  Future<AppMessage> acknowledge(AckAppMessageCommand command) {
    return client.notificationNotificationAckAppMessage(
      command,
      context: invocationContext(NotificationRequestPageIds.ackAppMessage),
    );
  }

  @override
  Future<AppMessage> markRead(ReadAppMessageCommand command) {
    return client.notificationNotificationReadAppMessage(
      command,
      context: invocationContext(NotificationRequestPageIds.readAppMessage),
    );
  }
}
