// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/presentation/assistant_presentation_renderer.dart';

void main() {
  patrolTest(
    '真实 Skill 输出由 Adaptive Presentation 原生渲染且保留可见答案',
    tags: const ['t4', 'assistant', 'gamma'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.assistant);

      final input = find.byKey(TestKeys.assistantChatInputField);
      await $(input).waitUntilVisible(timeout: const Duration(seconds: 30));
      await $(input).enterText('请为杭州两日公开景点行程给出结构化安排，保留可读的 Markdown 降级摘要。');
      await $(find.byKey(TestKeys.assistantSendButton)).tap();

      expect(
        await _waitFor(
          $,
          find.byType(AssistantPresentationRenderer),
          const Duration(seconds: 60),
        ),
        isTrue,
        reason: '支持 presentation capability 的真实 App 必须消费服务端语义文档',
      );
      expect(
        await _waitUntilAbsent(
          $,
          find.byKey(TestKeys.assistantStopGeneratingButton),
          const Duration(seconds: 60),
        ),
        isTrue,
        reason: '最终 Adaptive Presentation 必须随 canonical Run 终态一起提交',
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
