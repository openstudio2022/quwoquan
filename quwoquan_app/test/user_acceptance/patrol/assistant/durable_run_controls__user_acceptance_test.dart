// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

void main() {
  patrolTest(
    '真实持久 Run 可暂停、恢复并取消',
    tags: const ['t4', 'assistant', 'durable-run', 'gamma'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.assistant);

      final input = find.byKey(TestKeys.assistantChatInputField);
      await $(input).waitUntilVisible(timeout: const Duration(seconds: 30));
      await $(input).enterText(
        '请作为长任务依次核对 https://example.com 和其公开可访问链接，'
        '记录证据后再综合；在完成前保持任务可暂停。',
      );
      await $(find.byKey(TestKeys.assistantSendButton)).tap();

      expect(
        await _waitFor(
          $,
          find.byKey(TestKeys.assistantPauseRunButton),
          const Duration(seconds: 30),
        ),
        isTrue,
        reason: '运行中的 canonical AssistantRun 必须提供暂停动作',
      );
      await $(find.byKey(TestKeys.assistantPauseRunButton)).tap();
      expect(
        await _waitFor(
          $,
          find.byKey(TestKeys.assistantResumeRunButton),
          const Duration(seconds: 5),
        ),
        isTrue,
        reason: '暂停必须在 5 秒内确认并显示恢复动作',
      );

      await $(find.byKey(TestKeys.assistantResumeRunButton)).tap();
      expect(
        await _waitFor(
          $,
          find.byKey(TestKeys.assistantStopGeneratingButton),
          const Duration(seconds: 5),
        ),
        isTrue,
        reason: '恢复后同一 Run 必须重新进入可取消执行态',
      );
      await $(find.byKey(TestKeys.assistantStopGeneratingButton)).tap();
      expect(
        await _waitUntilAbsent(
          $,
          find.byKey(TestKeys.assistantStopGeneratingButton),
          const Duration(seconds: 10),
        ),
        isTrue,
        reason: '取消必须在 10 秒内收敛，且终态不再保留执行控制',
      );
    },
  );
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  Finder finder,
  Duration timeout,
) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}

Future<bool> _waitUntilAbsent(
  PatrolIntegrationTester $,
  Finder finder,
  Duration timeout,
) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isEmpty) return true;
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
