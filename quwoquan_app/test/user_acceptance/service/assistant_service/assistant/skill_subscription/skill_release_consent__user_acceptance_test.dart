// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

void main() {
  patrolTest(
    '旅行 Skill active release 可撤权并重新授权',
    tags: const ['user-acceptance', 'assistant', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.assistantSkills);

      final toggle = find.byKey(
        const ValueKey<String>('assistant_skill_toggle_travel_planning'),
      );
      await $(toggle).waitUntilVisible(timeout: const Duration(seconds: 30));
      expect(
        $.tester.widget<CupertinoSwitch>(toggle).value,
        isTrue,
        reason: 'Gamma 候选身份必须绑定已授权的旅行 Skill active release',
      );

      await $(toggle).tap();
      expect(
        await _waitForSwitchValue($, toggle, false),
        isTrue,
        reason: '撤权必须写入真实 Remote subscription，下一次运行立即生效',
      );

      await $(toggle).tap();
      expect(
        await _waitForSwitchValue($, toggle, true),
        isTrue,
        reason: '恢复授权后同一 active release 必须重新可用',
      );
    },
  );
}

Future<bool> _waitForSwitchValue(
  PatrolIntegrationTester $,
  Finder finder,
  bool expected,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty &&
        $.tester.widget<CupertinoSwitch>(finder).value == expected) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
