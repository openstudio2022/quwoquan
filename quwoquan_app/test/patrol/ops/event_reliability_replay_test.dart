library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

void main() {
  patrolTest(
    'ops_event_reliability_replay',
    tags: ['t4', 'ops', 'replay'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await $(TestKeys.discoveryPage)
          .waitUntilVisible(timeout: const Duration(seconds: 20));

      for (var i = 0; i < 2; i++) {
        await $(TestKeys.discoveryCreateButton).tap();
        await $(TestKeys.createActionGallery)
            .waitUntilVisible(timeout: const Duration(seconds: 10));
        await $(TestKeys.createActionWrite).tap();
        await $(TestKeys.createPage)
            .waitUntilVisible(timeout: const Duration(seconds: 10));
        await $(TestKeys.createCloseButton).tap();
        await $(TestKeys.discoveryPage)
            .waitUntilVisible(timeout: const Duration(seconds: 10));
      }

      expect($(TestKeys.discoveryPage).visible, isTrue);
    },
  );
}
