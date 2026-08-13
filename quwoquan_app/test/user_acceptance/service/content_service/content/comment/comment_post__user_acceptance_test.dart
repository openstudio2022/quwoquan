// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-001
// readiness_case: comment_post_journey_app_uat
/// user_acceptance Patrol: 评论发布旅程
///
/// 对应 e2e.yaml 场景：comment_on_post_journey [test_type: ui_journey]
///
/// 守护：
///   - 评论输入（真实 IME 键盘 — flutter_test 无法替代）
///   - 评论出现在列表（500ms 内）
///   - commentCount +1
///   - rate limit 触发时：结构化恢复反馈可见 + 草稿保留且输入框重新 enabled
///
/// 注：每个用例自启动 App（launchPatrolAppOnce），对齐已绿的
///     home_recommendation_journey_test，不依赖 patrol_test_main 预启动。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

const _apiContractBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _cloudGatewayBase = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

String get _apiBase =>
    _apiContractBase.isNotEmpty ? _apiContractBase : _cloudGatewayBase;

const _testCommentText = 'Patrol E2E test comment 测试评论 🎯';

// ─── Tests ────────────────────────────────────────────────────────────────

void main() {
  setUp(() {
    assert(
      _apiContractEnv == 'gamma',
      'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
    );
    assert(
      _apiBase.isNotEmpty,
      'Patrol user_acceptance tests require API_CONTRACT_BASE_URL',
    );
    // app_gamma_seed_manifest.json 已预置 content_discovery_core /
    // fixture_photo_001；测试禁止通过退役 create route 自 seed。
  });

  patrolTest(
    'comment_on_post_journey — 发表评论 + commentCount +1',
    tags: ['user-acceptance', 'content', 'comment'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // ── 等待发现页并导航到帖子详情 ──────────────────────────────────
      await $(
        TestKeys.photoPostCard,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
      await $(TestKeys.photoPostCard).tap();
      await $.pumpAndSettle();

      // ── 读取初始 commentCount ─────────────────────────────────────────
      final countBefore =
          int.tryParse($(TestKeys.commentCountText).text ?? '0') ?? 0;

      // ── tap 评论输入框 ────────────────────────────────────────────────
      await $(
        TestKeys.commentInputBar,
      ).waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.commentInputBar).tap();

      // ── 真实 IME 输入（Patrol 专属能力）──────────────────────────────
      await $(
        TestKeys.commentTextField,
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      await $(TestKeys.commentTextField).enterText(_testCommentText);
      await $.pumpAndSettle();

      // iOS 可能弹出通知权限弹窗，dismiss 它
      if (await $.platform.mobile.isPermissionDialogVisible(
        timeout: const Duration(seconds: 3),
      )) {
        await $.platform.mobile.denyPermission();
      }

      // ── tap Submit ────────────────────────────────────────────────────
      await $(
        TestKeys.submitCommentButton,
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      await $(TestKeys.submitCommentButton).tap();
      await $.pumpAndSettle();

      // ── 断言：评论出现在列表 ──────────────────────────────────────────
      await $(
        find.text(_testCommentText),
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      expect(
        $(find.text(_testCommentText)).visible,
        isTrue,
        reason: 'New comment must appear in the comment thread',
      );

      // ── 断言：commentCount +1 ─────────────────────────────────────────
      final countAfter =
          int.tryParse($(TestKeys.commentCountText).text ?? '0') ?? 0;
      expect(
        countAfter,
        countBefore + 1,
        reason: 'commentCount must increment by 1 after posting',
      );
    },
  );

  patrolTest(
    'comment_on_post_journey — rate limit 反馈可见 + 草稿保留且输入框重新 enabled',
    tags: ['user-acceptance', 'content', 'comment'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      await launchPatrolAppOnce($);

      await $(
        TestKeys.photoPostCard,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
      await $(TestKeys.photoPostCard).tap();
      await $.pumpAndSettle();

      // gamma 使用商用默认 burst policy：30 秒最多 5 条。独立用例必须自行提交
      // max+1 次，不得依赖前一个测试已经消耗配额。
      var rateLimitFeedbackVisible = false;
      var rejectedDraft = '';
      for (var i = 0; i < 6; i++) {
        await $(
          TestKeys.commentInputBar,
        ).waitUntilVisible(timeout: const Duration(seconds: 5));
        await $(TestKeys.commentInputBar).tap();
        await $(
          TestKeys.commentTextField,
        ).waitUntilVisible(timeout: const Duration(seconds: 5));
        rejectedDraft = '频控恢复验证 $i';
        await $(TestKeys.commentTextField).enterText(rejectedDraft);
        await $(TestKeys.submitCommentButton).tap();
        await $.pumpAndSettle();
        if (find.byType(CupertinoAlertDialog).evaluate().isNotEmpty) {
          rateLimitFeedbackVisible = true;
          break;
        }
      }

      expect(
        rateLimitFeedbackVisible,
        isTrue,
        reason: 'The sixth request must show structured rate-limit feedback',
      );

      // 失败不能关闭输入态或清掉用户草稿；用户可稍后直接重试。
      final field = $.tester.widget<CupertinoTextField>(
        find.byKey(TestKeys.commentTextField),
      );
      expect(field.enabled, isTrue);
      expect(field.controller?.text, rejectedDraft);
    },
  );
}
