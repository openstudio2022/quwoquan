import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_request_page_ids.g.dart';

void main() {
  group('Notification metadata contract', () {
    test('service.yaml generated paths stay aligned', () {
      expect(NotificationApiMetadata.domain, 'notification');
      expect(NotificationApiMetadata.listNotificationsPath, '/v1/notifications');
      expect(NotificationApiMetadata.getUnreadCountPath, '/v1/notifications/unread-count');
      expect(NotificationApiMetadata.markAsReadPath, '/v1/notifications/read');
      expect(NotificationApiMetadata.markAllAsReadPath, '/v1/notifications/read-all');
    });

    test('request page ids stay aligned', () {
      expect(
        NotificationRequestPageIds.operationToPageId['ListNotifications'],
        NotificationRequestPageIds.listNotifications,
      );
      expect(
        NotificationRequestPageIds.operationToPageId['GetUnreadCount'],
        NotificationRequestPageIds.getUnreadCount,
      );
      expect(
        NotificationRequestPageIds.operationToPageId['MarkAsRead'],
        NotificationRequestPageIds.markAsRead,
      );
      expect(
        NotificationRequestPageIds.operationToPageId['MarkAllAsRead'],
        NotificationRequestPageIds.markAllAsRead,
      );
    });
  });
}
