/// T4 Patrol E2E: 动作优先创作入口
///
/// 守护：发现页创作按钮进入三动作入口，再进入统一编辑器。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

import '../support/home_create_entry.dart';

void main() {
  patrolTest(
    'create_entry_start_actions — 底部导航「+」进入三动作入口并可进入统一编辑器',
    tags: ['t4', 'content', 'create'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);

      expect($(TestKeys.createActionWrite).visible, isTrue);
      expect($(TestKeys.createActionCapture).visible, isTrue);

      await $(TestKeys.createActionWrite).tap();
      await $(
        TestKeys.createPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      expect($(TestKeys.createMomentInput).visible, isTrue);
    },
  );
}
