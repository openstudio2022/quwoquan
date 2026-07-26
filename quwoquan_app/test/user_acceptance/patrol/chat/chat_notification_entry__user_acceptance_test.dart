/// user_acceptance Patrol: 真实系统通知点击打开指定聊天详情。
///
/// 外部设备编排器必须在 `QWQ_CHAT_NOTIFICATION_UAT_READY` 出现后投递带唯一
/// correlation 文案的真实 Push。本用例不允许在通知缺失时降格为“不崩溃”通过。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _expectedConversationId = String.fromEnvironment(
  'CHAT_NOTIFICATION_EXPECTED_CONVERSATION_ID',
);
const _expectedNotificationText = String.fromEnvironment(
  'CHAT_NOTIFICATION_EXPECTED_TEXT',
);
const _notificationCorrelationId = String.fromEnvironment(
  'CHAT_NOTIFICATION_CORRELATION_ID',
);

void main() {
  patrolTest(
    '后台真实 Push 点击后打开指定聊天详情',
    tags: ['t4', 'chat', 'notification'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 30)),
    ($) async {
      expect(
        _apiContractEnv == 'gamma',
        isTrue,
        reason:
            'notification UAT must run against the Gamma Remote environment',
      );
      expect(
        _expectedConversationId.trim(),
        isNotEmpty,
        reason: 'the device orchestrator must inject the expected conversation',
      );
      expect(
        _expectedNotificationText.trim(),
        isNotEmpty,
        reason:
            'the device orchestrator must inject a unique notification text',
      );
      expect(
        _notificationCorrelationId.trim(),
        isNotEmpty,
        reason: 'the device orchestrator must inject a unique correlation id',
      );

      await launchPatrolAppOnce($);
      await $(
        find.byType(WidgetsApp),
      ).waitUntilVisible(timeout: const Duration(seconds: 30));

      await $.platform.mobile.pressHome();
      // 设备编排器以此稳定标记为投递起点；标记只含随机 correlation，不含 token/PII。
      // ignore: avoid_print
      print('QWQ_CHAT_NOTIFICATION_UAT_READY:$_notificationCorrelationId');

      final deadline = DateTime.now().add(const Duration(seconds: 30));
      var matched = false;
      while (DateTime.now().isBefore(deadline) && !matched) {
        final notifications = await $.platform.mobile.getNotifications();
        matched = notifications.any(
          (notification) =>
              notification.title.contains(_expectedNotificationText) ||
              notification.content.contains(_expectedNotificationText),
        );
        if (!matched) {
          await Future<void>.delayed(const Duration(milliseconds: 500));
        }
      }
      expect(
        matched,
        isTrue,
        reason: 'the expected correlated system notification must be delivered',
      );

      await $.platform.mobile.openNotifications();
      await $.platform.mobile.tapOnNotificationBySelector(
        Selector(textContains: _expectedNotificationText),
      );

      final expectedPage = find.byWidgetPredicate(
        (widget) =>
            widget is ChatConversationPage &&
            widget.conversationId == _expectedConversationId,
      );
      await $(
        expectedPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 30));
      expect(expectedPage, findsOneWidget);
    },
  );
}
