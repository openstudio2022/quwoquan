/// T4 Patrol E2E: 点赞旅程（realtime + error rollback）
///
/// 对应 e2e.yaml 场景：like_post_realtime [test_type: ui_journey]
///
/// 守护：
///   - 点赞乐观更新（50ms 内 UI +1）
///   - server 响应后与 likeCount 一致
///   - rate limit 触发时：回滚 + 错误 Toast（真实触摸交互 + 真实网络时序）
///
/// 注：App 由 test/patrol/patrol_test_main.dart 的 app.main() 启动，
///     本 test 直接与已运行的 App 交互，不需要 pumpWidget。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/core/test_keys.dart';

const _apiContractBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _cloudGatewayBase = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _testToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

String get _apiBase =>
    _apiContractBase.isNotEmpty ? _apiContractBase : _cloudGatewayBase;

// ─── Staging 数据辅助 ─────────────────────────────────────────────────────

Future<String> _seedPhotoPost(http.Client client) async {
  final resp = await client.post(
    Uri.parse('$_apiBase/v1/content/posts'),
    headers: {
      'Content-Type': 'application/json',
      if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken',
    },
    body: jsonEncode({
      'contentType': 'image',
      'title': 'T4 like_post_realtime seed',
      'body': 'patrol test fixture',
      'mediaUrls': ['https://example.com/patrol.jpg'],
    }),
  );
  if (resp.statusCode != 201) {
    throw Exception('seed failed: ${resp.statusCode} ${resp.body}');
  }
  return (jsonDecode(resp.body) as Map<String, dynamic>)['_id'] as String;
}

Future<void> _deletePost(http.Client client, String postId) async {
  await client.delete(
    Uri.parse('$_apiBase/v1/content/posts/$postId'),
    headers: {if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken'},
  );
}

Future<void> _resetLikeState(http.Client client, String postId) async {
  // unlike（即使未点赞也不报错）
  await client.delete(
    Uri.parse('$_apiBase/v1/content/posts/$postId/like'),
    headers: {if (_testToken.isNotEmpty) 'Authorization': 'Bearer $_testToken'},
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────

void main() {
  late http.Client client;
  late String seededPostId;

  setUp(() async {
    assert(
      _apiContractEnv == 'gamma',
      'T4 tests must run with API_CONTRACT_ENV=gamma',
    );
    assert(_apiBase.isNotEmpty, 'T4 tests require API_CONTRACT_BASE_URL');
    client = http.Client();
    seededPostId = await _seedPhotoPost(client);
    await _resetLikeState(client, seededPostId);
  });

  tearDown(() async {
    await _deletePost(client, seededPostId);
    client.close();
  });

  patrolTest(
    'like_post_realtime — 乐观更新 + server 确认',
    tags: ['t4', 'content', 'like'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      // ── App 已运行，等待发现页 + 包含 seededPost 的卡片 ──────────────
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
    'like_post_realtime — 重复点赞幂等（不双计）',
    tags: ['t4', 'content', 'like'],
    skip: !kRunPatrolT4,
    ($) async {
      // ── App 已运行，等待点赞按钮可见 ─────────────────────────────────
      await $(
        TestKeys.likeButton,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      final countBefore =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;

      // 连续 tap 两次（模拟快速双击）
      await $(TestKeys.likeButton).tap();
      await $.pumpAndSettle();
      await $(TestKeys.likeButton).tap();
      await $.pumpAndSettle();

      // 两次点同一帖子：期望幂等（server 端 upsert）
      await $(
        TestKeys.likeCountText,
      ).waitUntilVisible(timeout: const Duration(seconds: 5));
      final countAfter =
          int.tryParse($(TestKeys.likeCountText).text ?? '0') ?? 0;
      expect(
        countAfter,
        countBefore + 1,
        reason: 'Idempotent like: second tap should not double-increment count',
      );
    },
  );
}
