/// T4 Patrol E2E: 创作草稿保存与恢复
///
/// 守护：动作优先入口进入统一编辑器，保存草稿后再次进入仍可恢复。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

import '../support/home_create_entry.dart';

const _draftText = 'patrol 草稿恢复内容';

void main() {
  patrolTest(
    'content_draft_preservation — 保存并退出后可恢复草稿',
    tags: ['t4', 'content', 'draft'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // 创作入口已迁移到底部导航「+」（DiscoveryPage 已不在主导航）。
      await openCreateActionSheet($);
      await $(TestKeys.createActionWrite).tap();

      await $(
        TestKeys.createPage,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createMomentInput).enterText(_draftText);
      await $(TestKeys.createCloseButton).tap();
      await $(TestKeys.createSaveAndExitButton).tap();

      await waitForHomeShell($);

      await openCreateActionSheet($);
      await $(
        TestKeys.createActionContinueFromDraft,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.createActionContinueFromDraft).tap();
      await $(
        TestKeys.createDraftPickerPanel,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      // 点选「文字草稿」恢复草稿（draftLabel：无标题/无图的文字草稿 == '文字草稿'）。
      // 草稿恢复需关闭选择面板 + 重建统一编辑器路由，gamma 上较慢，给足 settle 与超时。
      await $('文字草稿').tap();
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));

      // 恢复后编辑器载入草稿正文 → 文档非空，空文档占位输入框
      // (TestKeys.createMomentInput) 不再渲染；直接断言草稿正文可见，
      // 这才是「草稿可恢复」的真实证据。
      await $(
        find.text(_draftText),
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
      expect($(find.text(_draftText)).visible, isTrue);
    },
  );
}
