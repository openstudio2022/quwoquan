// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
// readiness_case: notification_list_app_messages_app_local
// readiness_case: notification_get_app_message_app_local
// readiness_case: notification_get_app_message_unread_count_app_local
// readiness_case: notification_ack_app_message_app_local
// readiness_case: notification_read_app_message_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/notification/notification_request_page_ids.g.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/adapters/app_message_facets_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

Map<String, Object?> _appMessageWire({
  bool read = false,
  bool acknowledged = false,
}) => <String, Object?>{
  'messageId': 'message-notification',
  'userId': 'account-notification',
  'messageType': 'content',
  'source': 'comment',
  'sourceId': 'comment-notification',
  'destination': <String, Object?>{
    'type': 'user',
    'id': 'account-notification',
  },
  'title': '新的评论',
  'summary': '评论了你的作品',
  'target': <String, Object?>{
    'targetType': 'post',
    'targetId': 'post-notification',
    'query': <String, Object?>{},
  },
  'read': read,
  'createdAt': '2026-08-08T08:00:00Z',
  'deliveredAt': '2026-08-08T08:00:01Z',
  if (acknowledged) 'ackedAt': '2026-08-08T08:00:02Z',
  if (read) 'readAt': '2026-08-08T08:00:03Z',
};

http.Response _notificationResponseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' && path == '/app-messages') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_appMessageWire()],
      'nextCursor': 'notification-cursor-2',
    });
  }
  if (request.method == 'GET' && path == '/app-messages/unread-count') {
    return remoteApiPathJsonResponse(<String, Object?>{'unreadCount': 1});
  }
  if (request.method == 'GET' && path == '/app-messages/message-notification') {
    return remoteApiPathJsonResponse(_appMessageWire());
  }
  if (request.method == 'POST' &&
      path == '/app-messages/message-notification/ack') {
    return remoteApiPathJsonResponse(_appMessageWire(acknowledged: true));
  }
  if (request.method == 'POST' &&
      path == '/app-messages/message-notification/read') {
    return remoteApiPathJsonResponse(_appMessageWire(read: true));
  }
  throw StateError('unexpected notification request: ${request.method} $path');
}

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

    test(
      'production Remote 单轨编码 inbox 五个 operation 并解析 typed result',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final adapter = RemoteAppMessageAdapter(
          client: buildRemoteApiPathOperationClient(
            log,
            responseFor: _notificationResponseFor,
          ),
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.chatList.id,
            routeId: AppUiSurfaces.chatList.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-notification',
              personaId: 'persona-notification',
            ),
          ),
        );

        final listed = await adapter.listAppMessages(
          ListAppMessagesQuery(
            messageType: NotificationType.content.wireName,
            read: false,
            cursor: 'notification-cursor-1',
            limit: 7,
          ),
        );
        final unread = await adapter.getUnreadCount(
          const GetAppMessageUnreadCountQuery(),
        );
        final fetched = await adapter.getAppMessage(
          const GetAppMessageQuery(messageId: 'message-notification'),
        );
        final acknowledged = await adapter.acknowledge(
          const AckAppMessageCommand(messageId: 'message-notification'),
        );
        final read = await adapter.markRead(
          const ReadAppMessageCommand(messageId: 'message-notification'),
        );

        expect(listed.items.single.messageId, 'message-notification');
        expect(listed.nextCursor, 'notification-cursor-2');
        expect(unread.unreadCount, 1);
        expect(fetched.target.targetId, 'post-notification');
        expect(acknowledged.ackedAt, DateTime.utc(2026, 8, 8, 8, 0, 2));
        expect(read.read, isTrue);
        expect(read.readAt, DateTime.utc(2026, 8, 8, 8, 0, 3));

        expect(log.map((request) => request.method), <String>[
          'GET',
          'GET',
          'GET',
          'POST',
          'POST',
        ]);
        expect(log.map((request) => request.path), <String>[
          '/app-messages',
          '/app-messages/unread-count',
          '/app-messages/message-notification',
          '/app-messages/message-notification/ack',
          '/app-messages/message-notification/read',
        ]);
        expect(log.first.query, <String, String>{
          'type': 'content',
          'read': 'false',
          'cursor': 'notification-cursor-1',
          'limit': '7',
        });
        expect(log.skip(1).every((request) => request.query.isEmpty), isTrue);
        expect(log.every((request) => request.body.isEmpty), isTrue);

        const operationIds = <String>[
          AppCloudOperationIds.notificationNotificationListAppMessages,
          AppCloudOperationIds.notificationNotificationGetAppMessageUnreadCount,
          AppCloudOperationIds.notificationNotificationGetAppMessage,
          AppCloudOperationIds.notificationNotificationAckAppMessage,
          AppCloudOperationIds.notificationNotificationReadAppMessage,
        ];
        const pageIds = <String>[
          NotificationRequestPageIds.listAppMessages,
          NotificationRequestPageIds.getAppMessageUnreadCount,
          NotificationRequestPageIds.getAppMessage,
          NotificationRequestPageIds.ackAppMessage,
          NotificationRequestPageIds.readAppMessage,
        ];
        for (var index = 0; index < log.length; index += 1) {
          expectRemoteApiPathHeaders(
            log[index].headers,
            clientPageId: pageIds[index],
            surfaceId: AppUiSurfaces.chatList.id,
            operationId: operationIds[index],
          );
        }

        expect(
          operationIds.map(
            (operationId) =>
                canonicalRemoteApiOperation(operationId).idempotency,
          ),
          <String>['optional', 'none', 'optional', 'none', 'none'],
        );
      },
    );
  });
}
