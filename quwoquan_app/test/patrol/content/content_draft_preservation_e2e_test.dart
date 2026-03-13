/// L4 Patrol E2E: 创作草稿保存与恢复
///
/// 守护：动作优先入口进入统一编辑器，保存草稿后再次进入仍可恢复。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/test_keys.dart';

const _draftText = 'patrol 草稿恢复内容';

void main() {
  patrolTest(
    'content_draft_preservation — 保存并退出后可恢复草稿',
    tags: ['l4', 'content', 'draft'],
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await $(
        TestKeys.discoveryPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      await $(TestKeys.discoveryCreateButton).tap();
      await $(
        TestKeys.createActionWrite,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createActionWrite).tap();

      await $(
        TestKeys.createPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createMomentInput).enterText(_draftText);
      await $(TestKeys.createCloseButton).tap();
      await $(TestKeys.createSaveAndExitButton).tap();

      await $(
        TestKeys.discoveryPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));

      await $(TestKeys.discoveryCreateButton).tap();
      await $(
        TestKeys.createActionWrite,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createActionWrite).tap();

      await $(
        TestKeys.createDraftsButton,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createDraftsButton).tap();
      await $('点滴草稿').tap();

      await $(
        TestKeys.createMomentInput,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      expect($(find.text(_draftText)).visible, isTrue);
    },
  );
}
