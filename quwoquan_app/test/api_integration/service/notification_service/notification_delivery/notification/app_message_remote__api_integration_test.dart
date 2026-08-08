// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
// readiness_case: notification_list_app_messages_app_api
// readiness_case: notification_get_app_message_unread_count_app_api
// readiness_case: notification_get_app_message_app_api
// readiness_case: notification_ack_app_message_app_api
// readiness_case: notification_read_app_message_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/notification/notification_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/notification_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

Future<AppMessage> _waitForGreetingMessage({
  required NotificationApiContractHarness harness,
  required String greetingId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    final slice = await harness.query.listAppMessages(
      ListAppMessagesQuery(read: false, limit: 100),
    );
    for (final message in slice.items) {
      if (message.source == 'greeting' && message.sourceId == greetingId) {
        return message;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
  throw StateError(
    'GreetingRequest $greetingId was not projected into AppMessage inbox',
  );
}

Matcher _appMessageNotFound() {
  return isA<CloudException>()
      .having(
        (error) => error.runtimeFailure.code,
        'runtime failure code',
        NotificationErrorCode.appMessageNotFound.code,
      )
      .having((error) => error.statusCode, 'status code', 404);
}

void main() {
  test('generated Remote 列出 AppMessage inbox slice', () async {
    final harness = await NotificationApiContractHarness.create();
    addTearDown(harness.close);
    final stopwatch = Stopwatch()..start();
    final slice = await harness.query.listAppMessages(
      ListAppMessagesQuery(read: false, limit: 20),
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(slice.items.length, lessThanOrEqualTo(20));
    expect(
      slice.items.every(
        (message) =>
            !message.read &&
            message.messageId.trim().isNotEmpty &&
            message.userId == harness.session.ownerId &&
            message.source.trim().isNotEmpty &&
            message.sourceId.trim().isNotEmpty,
      ),
      isTrue,
    );

    final events = await harness.telemetry.waitForEvents(minimumCount: 2);
    final event = events.singleWhere(
      (candidate) =>
          candidate.canonicalOperationId ==
          AppCloudOperationIds.notificationNotificationListAppMessages,
    );
    expect(event.succeeded, isTrue);
    expect(event.statusCode, 200);
    expect(event.requestId.trim(), isNotEmpty);
    expect(event.traceId.trim(), isNotEmpty);
  });

  test('generated Remote 返回 unread count slice', () async {
    final harness = await NotificationApiContractHarness.create();
    addTearDown(harness.close);
    final unread = await harness.query.getUnreadCount(
      GetAppMessageUnreadCountQuery(),
    );

    expect(unread.unreadCount, greaterThanOrEqualTo(0));

    final events = await harness.telemetry.waitForEvents(minimumCount: 2);
    final event = events.singleWhere(
      (candidate) =>
          candidate.canonicalOperationId ==
          AppCloudOperationIds.notificationNotificationGetAppMessageUnreadCount,
    );
    expect(event.succeeded, isTrue);
    expect(event.statusCode, 200);
    expect(event.requestId.trim(), isNotEmpty);
    expect(event.traceId.trim(), isNotEmpty);
  });

  test(
    '公开 GreetingRequest 投影后 Get、Ack、Read 按 AccountID 收敛',
    () async {
      final notification = await NotificationApiContractHarness.create();
      addTearDown(notification.close);
      final user = await UserApiContractHarness.create();
      addTearDown(user.close);
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final target = notification.session;
      final requester = await user.loginDisposableAccount(
        'notification-greeting-requester-$suffix',
      );
      var requesterClosed = false;
      var targetClosed = false;

      Future<void> closeAccount(
        AuthSessionGrant session,
        String requestId,
      ) async {
        await user.withSession(
          session: session,
          action: () => user.accountLifecycle.closeAccount(
            CloseAccountCommand(clientRequestId: requestId),
          ),
        );
      }

      addTearDown(() async {
        final failures = <Object>[];
        if (!targetClosed) {
          try {
            await closeAccount(target, 'notification-target-cleanup-$suffix');
          } on Object catch (error) {
            failures.add(error);
          }
        }
        if (!requesterClosed) {
          try {
            await closeAccount(
              requester,
              'notification-requester-cleanup-$suffix',
            );
          } on Object catch (error) {
            failures.add(error);
          }
        }
        if (failures.isNotEmpty) {
          throw StateError('account cleanup failed: $failures');
        }
      });

      final targetPersonaId = target.activePersona!.personaId;
      final sent = await user.withSession(
        session: requester,
        action: () => user.withIdempotencyKey(
          idempotencyKey: 'notification-greeting-send-$suffix',
          action: () => user.greetingRequests.sendGreeting(
            SendGreetingCommand(
              targetPersonaId: targetPersonaId,
              requestMessage: 'Notification API contract $suffix',
              source: 'profile',
            ),
          ),
        ),
      );
      expect(sent.targetPersonaId, targetPersonaId);

      final projected = await _waitForGreetingMessage(
        harness: notification,
        greetingId: sent.id,
      );
      expect(projected.userId, target.ownerId);
      expect(projected.userId, isNot(targetPersonaId));
      expect(projected.read, isFalse);
      expect(projected.ackedAt, isNull);

      final unreadBefore = await notification.query.getUnreadCount(
        GetAppMessageUnreadCountQuery(),
      );
      expect(unreadBefore.unreadCount, greaterThanOrEqualTo(1));

      Future<void> expectRequesterNotFound(
        Future<Object?> Function() action,
      ) async {
        await expectLater(
          notification.withSession(session: requester, action: action),
          throwsA(_appMessageNotFound()),
        );
      }

      final messageId = projected.messageId;
      await expectRequesterNotFound(
        () => notification.query.getAppMessage(
          GetAppMessageQuery(messageId: messageId),
        ),
      );
      await expectRequesterNotFound(
        () => notification.commandWriter.acknowledge(
          AckAppMessageCommand(messageId: messageId),
        ),
      );
      await expectRequesterNotFound(
        () => notification.commandWriter.markRead(
          ReadAppMessageCommand(messageId: messageId),
        ),
      );

      final detail = await notification.query.getAppMessage(
        GetAppMessageQuery(messageId: messageId),
      );
      expect(detail.messageId, messageId);
      expect(detail.userId, target.ownerId);
      expect(detail.source, 'greeting');
      expect(detail.sourceId, sent.id);
      expect(detail.read, isFalse);
      expect(detail.ackedAt, isNull);

      final acknowledged = await notification.commandWriter.acknowledge(
        AckAppMessageCommand(messageId: messageId),
      );
      final acknowledgeReplay = await notification.commandWriter.acknowledge(
        AckAppMessageCommand(messageId: messageId),
      );
      expect(acknowledged.userId, target.ownerId);
      expect(acknowledged.read, isFalse);
      expect(acknowledged.ackedAt, isNotNull);
      expect(acknowledgeReplay.ackedAt, acknowledged.ackedAt);

      final read = await notification.commandWriter.markRead(
        ReadAppMessageCommand(messageId: messageId),
      );
      final readReplay = await notification.commandWriter.markRead(
        ReadAppMessageCommand(messageId: messageId),
      );
      expect(read.userId, target.ownerId);
      expect(read.read, isTrue);
      expect(read.readAt, isNotNull);
      expect(read.ackedAt, acknowledged.ackedAt);
      expect(readReplay.readAt, read.readAt);

      final converged = await notification.query.getAppMessage(
        GetAppMessageQuery(messageId: messageId),
      );
      expect(converged.read, isTrue);
      expect(converged.readAt, read.readAt);
      expect(converged.ackedAt, acknowledged.ackedAt);
      final unreadAfter = await notification.query.getUnreadCount(
        GetAppMessageUnreadCountQuery(),
      );
      expect(unreadAfter.unreadCount, lessThan(unreadBefore.unreadCount));

      final events = await notification.telemetry.waitForEvents(
        minimumCount: 13,
      );
      for (final operationId in <String>{
        AppCloudOperationIds.notificationNotificationGetAppMessage,
        AppCloudOperationIds.notificationNotificationAckAppMessage,
        AppCloudOperationIds.notificationNotificationReadAppMessage,
      }) {
        final operationEvents = events
            .where((event) => event.canonicalOperationId == operationId)
            .toList(growable: false);
        expect(operationEvents.any((event) => event.succeeded), isTrue);
        expect(operationEvents.any((event) => !event.succeeded), isTrue);
        expect(
          operationEvents.every(
            (event) =>
                event.requestId.trim().isNotEmpty &&
                event.traceId.trim().isNotEmpty &&
                (event.statusCode == 200 || event.statusCode == 404),
          ),
          isTrue,
        );
      }

      await closeAccount(target, 'notification-target-cleanup-$suffix');
      targetClosed = true;
      await closeAccount(requester, 'notification-requester-cleanup-$suffix');
      requesterClosed = true;
    },
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
