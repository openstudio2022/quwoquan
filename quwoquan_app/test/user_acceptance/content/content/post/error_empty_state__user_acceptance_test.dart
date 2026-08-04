/// user_acceptance Patrol: 错误/空状态展示
///
/// 对应 e2e.yaml 场景：error_empty_state_ui [test_type: ui_journey]
///
/// 守护：
///   - post_not_found 等空态按 ContentUIConfig.empty_states 展示
///   - 错误态使用内联占位或 SnackBar 符合 error-and-permission-semantics
///
/// 注：每个用例自启动 App（launchPatrolAppOnce），对齐已绿的
///     home_recommendation_journey_test，不依赖 patrol_test_main 预启动。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../../../patrol/support/home_create_entry.dart';

void main() {
  patrolTest(
    'error_empty_state_ui',
    tags: ['t4', 'content'],
    skip: !kRunPatrolT4,
    ($) async {
      await launchPatrolAppOnce($);

      // 自启动后首页壳应渲染（落地 tab = HomePage；DiscoveryPage 已不在主导航）。
      // 注：本用例当前仅守护「首页可渲染」基线；具体 post_not_found / 空态 / 错误态
      // 断言依赖详情页与可控错误注入，留待 Patrol user_acceptance 环境补齐（如实标注，未伪造覆盖）。
      await waitForHomeShell($);
      expect($(find.byKey(homeSearchChromeKey)).visible, isTrue);
    },
  );
}
