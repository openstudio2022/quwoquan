/// T4 Patrol E2E: 发现页 Feed 加载旅程
///
/// 对应 e2e.yaml 场景：discovery_feed_load_and_render [test_type: ui_journey]
///
/// 守护：发现页全链路（app → gamma → content-service）可渲染内容卡片
/// 只测 flutter_test 无法替代的行为：真实网络请求、真实设备渲染
///
/// 注：App 由 test/patrol/patrol_test_main.dart 的 app.main() 启动，
///     本 test 直接与已运行的 App 交互，不需要 pumpWidget。
///
/// 执行方式（本地，需连接真机或模拟器）：
///   patrol test test/patrol/discovery/feed_load_test.dart \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=TEST_AUTH_TOKEN=YOUR_TOKEN
///
/// CI：由 .github/workflows/e2e.yaml 在 pre-release tag 时触发。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _firstFollowingFeedCardKey = ValueKey<String>('moment-feed-card-0');

// dart-define 注入
const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    'discovery_feed_load_and_render',
    tags: ['t4', 'discovery'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 10)),
    ($) async {
      await launchPatrolAppOnce($);

      assert(
        _apiContractEnv == 'gamma',
        'T4 tests must run with API_CONTRACT_ENV=gamma',
      );

      // ── 等待首页 Following feed 渲染（冷启动需留足时间）───────────────
      await $(
        _firstFollowingFeedCardKey,
      ).waitUntilVisible(timeout: const Duration(seconds: 20));

      expect(
        $(_firstFollowingFeedCardKey).visible,
        isTrue,
        reason: 'At least one following feed card must be visible after load',
      );
    },
  );
}
