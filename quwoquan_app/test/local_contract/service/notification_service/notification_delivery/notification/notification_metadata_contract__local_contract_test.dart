// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/notification/notification_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('Notification metadata contract', () {
    test('service.yaml generated paths stay aligned', () {
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.notificationNotificationListAppMessages,
        ).domain,
        'notification',
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.notificationNotificationListAppMessages,
        ),
        '/app-messages',
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.notificationNotificationGetAppMessageUnreadCount,
        ),
        '/app-messages/unread-count',
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.notificationNotificationGetAppMessage,
          pathParameters: const <String, String>{'messageId': 'message/a'},
        ),
        '/app-messages/message%2Fa',
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.notificationNotificationAckAppMessage,
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        '/app-messages/message-a/ack',
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.notificationNotificationReadAppMessage,
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        '/app-messages/message-a/read',
      );
    });

    test(
      'canonical path rendering fails closed on identity/cardinality drift',
      () {
        expect(
          () => canonicalRemoteApiPath('notification.notification.Unknown'),
          throwsStateError,
        );
        expect(
          () => canonicalRemoteApiPath(
            AppCloudOperationIds.notificationNotificationGetAppMessage,
          ),
          throwsStateError,
        );
        expect(
          () => canonicalRemoteApiPath(
            AppCloudOperationIds.notificationNotificationGetAppMessage,
            pathParameters: const <String, String>{
              'messageId': 'message-a',
              'unexpected': 'value',
            },
          ),
          throwsStateError,
        );
        expect(
          () => canonicalRemoteApiPath(
            AppCloudOperationIds.notificationNotificationGetAppMessage,
            pathParameters: const <String, String>{'messageId': '  '},
          ),
          throwsStateError,
        );
        expect(
          () => canonicalRemoteApiPath(
            AppCloudOperationIds.notificationNotificationGetAppMessage,
            pathParameters: const <String, String>{'messageId': ' message-a '},
          ),
          throwsStateError,
        );
      },
    );

    test('canonical path rendering rejects malformed contract shapes', () {
      const requiredMessageBinding = CloudOperationRequestBinding(
        name: 'messageId',
        field: 'messageId',
        required: true,
      );

      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.MalformedPath',
          pathTemplate: '/app-messages/{messageId',
          requestPathBindings: const <CloudOperationRequestBinding>[
            requiredMessageBinding,
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.DuplicatePlaceholder',
          pathTemplate: '/app-messages/{messageId}/{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            requiredMessageBinding,
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.DuplicateBinding',
          pathTemplate: '/app-messages/{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            requiredMessageBinding,
            requiredMessageBinding,
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.OptionalPathBinding',
          pathTemplate: '/app-messages/{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            CloudOperationRequestBinding(
              name: 'messageId',
              field: 'messageId',
              required: false,
            ),
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.BlankPathBinding',
          pathTemplate: '/app-messages/{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            CloudOperationRequestBinding(
              name: '',
              field: 'messageId',
              required: true,
            ),
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.PaddedPathBinding',
          pathTemplate: '/app-messages/{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            CloudOperationRequestBinding(
              name: 'messageId',
              field: ' messageId ',
              required: true,
            ),
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.EmptySegment',
          pathTemplate: '/app-messages//{messageId}',
          requestPathBindings: const <CloudOperationRequestBinding>[
            requiredMessageBinding,
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
      expect(
        () => renderRemoteApiPathContractShapeForTest(
          operationId: 'notification.notification.TrailingSlash',
          pathTemplate: '/app-messages/{messageId}/',
          requestPathBindings: const <CloudOperationRequestBinding>[
            requiredMessageBinding,
          ],
          pathParameters: const <String, String>{'messageId': 'message-a'},
        ),
        throwsStateError,
      );
    });

    test('every canonical operation path shape is renderable', () {
      for (final entry in appCloudOperationContracts.entries) {
        final rendered = canonicalRemoteApiPath(
          entry.key,
          pathParameters: <String, String>{
            for (final binding in entry.value.requestPathBindings)
              binding.name: 'fixture-${binding.name}',
          },
        );
        expect(rendered, startsWith('/'), reason: entry.key);
        expect(rendered, isNot(contains('{')), reason: entry.key);
        expect(rendered, isNot(contains('}')), reason: entry.key);
      }
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
