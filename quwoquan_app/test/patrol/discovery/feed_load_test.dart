/// L4 Patrol E2E: 发现页 Feed 加载旅程
///
/// 对应 e2e.yaml 场景：discovery_feed_load_and_render [test_type: ui_journey]
///
/// 守护：发现页全链路（app → staging → content-service）可渲染内容卡片
/// 只测 flutter_test 无法替代的行为：真实网络请求、真实设备渲染
///
/// 注：App 由 integration_test/patrol_test_main.dart 的 app.main() 启动，
///     本 test 直接与已运行的 App 交互，不需要 pumpWidget。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test test/patrol/discovery/feed_load_test.dart \
///     --dart-define=ENV=staging \
///     --dart-define=TEST_AUTH_TOKEN=YOUR_TOKEN
///
/// CI：由 .github/workflows/e2e.yaml 在 pre-release tag 时触发。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/test_keys.dart';

// dart-define 注入
const _env = String.fromEnvironment('ENV', defaultValue: 'staging');

void main() {
  patrolTest(
    'discovery_feed_load_and_render',
    tags: ['l4', 'discovery'],
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 10),
    ),
    ($) async {
      // ── App 已由 patrol_test_main.dart 启动，直接交互 ────────────────
      assert(_env == 'staging', 'L4 tests must run with ENV=staging');

      // ── 等待发现页渲染（冷启动需留足时间）──────────────────────────────
      await $(TestKeys.discoveryPage)
          .waitUntilVisible(timeout: const Duration(seconds: 20));

      // ── 等待 photo feed grid 渲染 ────────────────────────────────────
      await $(TestKeys.photoFeedGrid)
          .waitUntilVisible(timeout: const Duration(seconds: 15));

      // ── 断言：至少 1 张 PhotoPostCard 可见 ───────────────────────────
      await $(TestKeys.photoPostCard)
          .waitUntilVisible(timeout: const Duration(seconds: 10));

      expect(
        $(TestKeys.photoPostCard).visible,
        isTrue,
        reason: 'At least one PhotoPostCard must be visible after feed loads',
      );
    },
  );
}
