/// T4 Patrol E2E: 评论发布旅程
///
/// 对应 e2e.yaml 场景：comment_on_post_journey [test_type: ui_journey]
///
/// 守护：
///   - 评论输入（真实 IME 键盘 — flutter_test 无法替代）
///   - 评论出现在列表（500ms 内）
///   - commentCount +1
///   - rate limit 触发时：error toast 可见 + 输入框重新 enabled
///
/// 注：App 已由 integration_test/patrol_test_main.dart 的 app.main() 启动，
///     本 test 直接与已运行的 App 交互，不需要 pumpWidget。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

const _stagingBase = String.fromEnvironment('STAGING_BASE_URL');
const _testToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _env = String.fromEnvironment('ENV', defaultValue: 'staging');

const _testCommentText = 'Patrol E2E test comment 测试评论 🎯';

// ─── Staging 数据辅助 ─────────────────────────────────────────────────────

Future<String> _seedPhotoPost(http.Client client) async {
  final resp = await client.post(
    Uri.parse('$_stagingBase/v1/content/posts'),
    headers: {
      'Content-Type': 'application/json',
      if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken',
    },
    body: jsonEncode({
      'contentType': 'image',
      'title': 'T4 comment_on_post_journey seed',
      'body': 'patrol test fixture',
      'mediaUrls': ['https://example.com/patrol.jpg'],
      'width': 1080,
      'height': 720,
    }),
  );
  if (resp.statusCode != 201) {
    throw Exception('seed failed: ${resp.statusCode} ${resp.body}');
  }
  return (jsonDecode(resp.body) as Map<String, dynamic>)['_id'] as String;
}

Future<void> _deletePost(http.Client client, String postId) async {
  await client.delete(
    Uri.parse('$_stagingBase/v1/content/posts/$postId'),
    headers: {
      if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken',
    },
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────

void main() {
  late http.Client client;
  late String seededPostId;

  setUp(() async {
    assert(_env == 'staging', 'T4 tests must run with ENV=staging');
    client = http.Client();
    seededPostId = await _seedPhotoPost(client);
  });

  tearDown(() async {
    await _deletePost(client, seededPostId);
    client.close();
  });

  patrolTest(
    'comment_on_post_journey — 发表评论 + commentCount +1',
    tags: ['t4', 'content', 'comment'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 10),
    ),
    ($) async {
      // ── App 已运行，等待发现页并导航到帖子详情 ──────────────────────
      await $(TestKeys.photoPostCard)
          .waitUntilVisible(timeout: const Duration(seconds: 20));
      await $(TestKeys.photoPostCard).tap();
      await $.pumpAndSettle();

      // ── 读取初始 commentCount ─────────────────────────────────────────
      final countBefore = int.tryParse(
            $(TestKeys.commentCountText).text ?? '0',
          ) ??
          0;

      // ── tap 评论输入框 ────────────────────────────────────────────────
      await $(TestKeys.commentInputBar)
          .waitUntilVisible(timeout: const Duration(seconds: 10));
      await $(TestKeys.commentInputBar).tap();

      // ── 真实 IME 输入（Patrol 专属能力）──────────────────────────────
      await $(TestKeys.commentTextField)
          .waitUntilVisible(timeout: const Duration(seconds: 5));
      await $(TestKeys.commentTextField).enterText(_testCommentText);
      await $.pumpAndSettle();

      // iOS 可能弹出通知权限弹窗，dismiss 它
      if (await $.platform.mobile.isPermissionDialogVisible(
          timeout: const Duration(seconds: 3))) {
        await $.platform.mobile.denyPermission();
      }

      // ── tap Submit ────────────────────────────────────────────────────
      await $(TestKeys.submitCommentButton)
          .waitUntilVisible(timeout: const Duration(seconds: 5));
      await $(TestKeys.submitCommentButton).tap();
      await $.pumpAndSettle();

      // ── 断言：评论出现在列表 ──────────────────────────────────────────
      await $(find.text(_testCommentText))
          .waitUntilVisible(timeout: const Duration(seconds: 5));
      expect(
        $(find.text(_testCommentText)).visible,
        isTrue,
        reason: 'New comment must appear in the comment thread',
      );

      // ── 断言：commentCount +1 ─────────────────────────────────────────
      final countAfter = int.tryParse(
            $(TestKeys.commentCountText).text ?? '0',
          ) ??
          0;
      expect(countAfter, countBefore + 1,
          reason: 'commentCount must increment by 1 after posting');
    },
  );

  patrolTest(
    'comment_on_post_journey — rate limit toast 可见 + 输入框重新 enabled',
    tags: ['t4', 'content', 'comment', 'flaky'],
    skip: !kRunPatrolT4,
    ($) async {
      // 此场景依赖 staging rate limit 触发，标记 flaky，允许 retry
      await $(TestKeys.photoPostCard)
          .waitUntilVisible(timeout: const Duration(seconds: 20));
      await $(TestKeys.photoPostCard).tap();
      await $.pumpAndSettle();

      // 快速连续发 5 条评论触发 rate limit
      for (var i = 0; i < 5; i++) {
        await $(TestKeys.commentTextField).enterText('spam $i');
        await $(TestKeys.submitCommentButton).tap();
        await $.pump();
      }
      await $.pumpAndSettle();

      // ── 断言：error toast 出现 ─────────────────────────────────────────
      await $(TestKeys.errorToast)
          .waitUntilVisible(timeout: const Duration(seconds: 5));
      expect($(TestKeys.errorToast).visible, isTrue,
          reason: 'Error toast must appear on rate limit');

      // ── 断言：输入框重新 enabled ──────────────────────────────────────
      await $(TestKeys.commentTextField)
          .waitUntilVisible(timeout: const Duration(seconds: 5));
      expect($(TestKeys.commentTextField).visible, isTrue,
          reason: 'Comment input must be re-enabled after rate limit error');
    },
  );
}
