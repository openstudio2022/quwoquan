library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../support/runtime/patrol/home_create_entry.dart';

void main() {
  patrolTest(
    'ops_event_reliability_replay',
    tags: ['user-acceptance', 'ops', 'replay'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      // 重复进入/退出编辑器，驱动行为事件多次产生与上报（可靠性回放）。
      for (var i = 0; i < 2; i++) {
        await openCreateActionSheet($);
        await $(TestKeys.createActionWrite).tap();
        await $(
          TestKeys.createPage,
        ).waitUntilVisible(timeout: const Duration(seconds: 10));
        await $(TestKeys.createCloseButton).tap();
        await waitForHomeShell($);
      }

      await waitForHomeShell($);
      expect($(find.byKey(homeSearchChromeKey)).visible, isTrue);
    },
  );
}
