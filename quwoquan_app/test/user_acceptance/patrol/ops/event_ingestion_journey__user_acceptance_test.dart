library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../support/home_create_entry.dart';

void main() {
  patrolTest(
    'ops_event_ingestion_journey',
    tags: ['t4', 'ops', 'event'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);

      await $(TestKeys.createActionWrite).tap();
      await $(TestKeys.createPage)
          .waitUntilVisible(timeout: const Duration(seconds: 10));

      expect($(TestKeys.createCloseButton).visible, isTrue);
      await $(TestKeys.createCloseButton).tap();
      await waitForHomeShell($);
    },
  );
}
