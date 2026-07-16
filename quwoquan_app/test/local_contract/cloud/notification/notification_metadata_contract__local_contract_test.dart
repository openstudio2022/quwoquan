import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/notification/notification_request_page_ids.g.dart';

void main() {
  group('Notification metadata contract', () {
    test('service.yaml generated paths stay aligned', () {
      expect(NotificationApiMetadata.domain, 'notification');
      expect(NotificationApiMetadata.listAppMessagesPath, '/v1/app-messages');
      expect(
        NotificationApiMetadata.getAppMessageUnreadCountPath,
        '/v1/app-messages/unread-count',
      );
      expect(
        NotificationApiMetadata.getAppMessagePath(messageId: 'message/a'),
        '/v1/app-messages/message%2Fa',
      );
      expect(
        NotificationApiMetadata.ackAppMessagePath(messageId: 'message-a'),
        '/v1/app-messages/message-a/ack',
      );
      expect(
        NotificationApiMetadata.readAppMessagePath(messageId: 'message-a'),
        '/v1/app-messages/message-a/read',
      );
    });

    test('request page ids stay aligned', () {
      expect(
        NotificationRequestPageIds.operationToPageId['ListAppMessages'],
        NotificationRequestPageIds.listAppMessages,
      );
      expect(
        NotificationRequestPageIds
            .operationToPageId['GetAppMessageUnreadCount'],
        NotificationRequestPageIds.getAppMessageUnreadCount,
      );
      expect(
        NotificationRequestPageIds.operationToPageId['AckAppMessage'],
        NotificationRequestPageIds.ackAppMessage,
      );
      expect(
        NotificationRequestPageIds.operationToPageId['ReadAppMessage'],
        NotificationRequestPageIds.readAppMessage,
      );
    });
  });
}
