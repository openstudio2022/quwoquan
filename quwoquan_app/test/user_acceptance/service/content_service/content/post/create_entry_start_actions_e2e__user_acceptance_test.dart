/// user_acceptance Patrol: 动作优先创作入口
///
/// 守护：发现页创作按钮进入三动作入口，再进入统一编辑器。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

import '../../../../../support/runtime/patrol/home_create_entry.dart';

void main() {
  patrolTest(
    'create_entry_start_actions — 底部导航「+」进入三动作入口并可进入统一编辑器',
    tags: ['user-acceptance', 'content', 'create'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);

      expect($(TestKeys.createActionPublishContent).visible, isTrue);
      expect($(TestKeys.createActionStartGathering).visible, isTrue);
      expect($(TestKeys.createActionStartGroupChat).visible, isTrue);

      await $(TestKeys.createActionPublishContent).tap();
      expect($(TestKeys.createActionGallery).visible, isTrue);
      expect($(TestKeys.createActionCapture).visible, isTrue);
      expect($(TestKeys.createActionWrite).visible, isTrue);
      await $(TestKeys.createActionWrite).tap();
      await $(
        TestKeys.createPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      expect($(TestKeys.createMomentInput).visible, isTrue);
    },
  );
}
