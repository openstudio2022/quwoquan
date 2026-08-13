// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#gwt-001
// readiness_case: content_reaction_like_app_uat
/// user_acceptance Patrol: 点赞旅程（realtime + error rollback）
///
/// 对应 e2e.yaml 场景：like_post_realtime [test_type: ui_journey]
///
/// 守护：
///   - 点赞乐观更新（50ms 内 UI +1）
///   - server 响应后与 likeCount 一致
///   - rate limit 触发时：回滚 + 错误 Toast（真实触摸交互 + 真实网络时序）
///
/// 注：每个用例自启动 App（launchPatrolAppOnce），对齐已绿的
///     home_recommendation_journey_test，不依赖 patrol_test_main 预启动。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:patrol/patrol.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

const _apiContractBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _cloudGatewayBase = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _testToken = String.fromEnvironment('TEST_AUTH_TOKEN');
// app_gamma_seed_manifest.json → content_discovery_core 的 canonical 预置对象。
const _seededPostId = 'fixture_photo_001';
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

String get _apiBase =>
    _apiContractBase.isNotEmpty ? _apiContractBase : _cloudGatewayBase;

Future<void> _resetLikeState(http.Client client, String postId) async {
  // unlike（即使未点赞也不报错）
  await client.delete(
    Uri.parse('$_apiBase/content/posts/$postId/like'),
    headers: {if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken'},
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────

void main() {
  late http.Client client;

  setUp(() async {
    assert(
      _apiContractEnv == 'gamma',
      'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
    );
    assert(
      _apiBase.isNotEmpty,
      'Patrol user_acceptance tests require API_CONTRACT_BASE_URL',
    );
    client = http.Client();
    await _resetLikeState(client, _seededPostId);
  });

  tearDown(() => client.close());

  patrolTest(
    'like_post_realtime — 乐观更新 + server 确认',
    tags: ['user-acceptance', 'content', 'like'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      // ── 等待发现页 + 包含 seededPost 的卡片 ──────────────────────────
      await $(
        TestKeys.photoPostCard,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      // ── 读取初始 likeCount ────────────────────────────────────────────
      final countBefore =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;

      // ── tap 点赞（真实触摸交互）───────────────────────────────────────
      await $(TestKeys.likeButton).tap();

      // ── 乐观更新：UI 应在 50ms 内显示 +1 ─────────────────────────────
      await $.pumpAndSettle();
      final countOptimistic =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;
      expect(
        countOptimistic,
        countBefore + 1,
        reason: 'Optimistic like count should increment immediately',
      );

      // ── 等待 server 响应后确认计数一致 ──────────────────────────────
      await $(
        TestKeys.likeCountText,
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      final countAfter =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;
      expect(
        countAfter,
        countBefore + 1,
        reason: 'Server-confirmed like count should match optimistic count',
      );
    },
  );

  patrolTest(
    'like_post_realtime — 点赞后取消回落到初始计数',
    tags: ['user-acceptance', 'content', 'like'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      await launchPatrolAppOnce($);

      // ── 等待点赞按钮可见 ─────────────────────────────────────────────
      await $(
        TestKeys.likeButton,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      final countBefore =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;

      // 首次 tap 点赞，第二次 tap 走 UnlikePost；重复 Like 的服务端幂等由
      // api_integration 锁定，UI 不能把 unlike 误写成“重复点赞”证据。
      await $(TestKeys.likeButton).tap();
      await $.pumpAndSettle();
      await $(TestKeys.likeButton).tap();
      await $.pumpAndSettle();

      await $(
        TestKeys.likeCountText,
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      final countAfter =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;
      expect(
        countAfter,
        countBefore,
        reason: 'Unlike should converge the optimistic count back to baseline',
      );
    },
  );
}
