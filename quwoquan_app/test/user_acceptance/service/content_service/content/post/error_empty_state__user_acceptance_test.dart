/// user_acceptance Patrol: 错误/空状态展示
///
/// 对应 e2e.yaml 场景：error_empty_state_ui [test_type: ui_journey]
///
/// 守护：
///   - 访问不存在的 Post（天然可控的 post_not_found 场景，无需错误注入）时，
///     production Remote 的 404 必须经 App error mapper 收敛为页面级错误态
///     （AppPageErrorState），而不是空白页、无限加载或崩溃。
///   - 首页壳在错误旅程前后均可渲染。
///
/// 注：每个用例自启动 App（launchPatrolAppOnce），对齐已绿的
///     home_recommendation_journey_test，不依赖 patrol_test_main 预启动。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import '../../../../../support/runtime/patrol/home_create_entry.dart';

void main() {
  patrolTest(
    'error_empty_state_ui',
    tags: ['user-acceptance', 'content'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      await launchPatrolAppOnce($);

      // 基线：首页壳可渲染。
      await waitForHomeShell($);
      expect($(find.byKey(homeSearchChromeKey)).visible, isTrue);

      // 真实错误旅程：访问不存在的 Post，production Remote 返回 not_found，
      // 页面必须收敛为错误态而不是空白或永久加载。
      final missingWorkId =
          'uat-missing-post-${DateTime.now().toUtc().microsecondsSinceEpoch}';
      await patrolGoTo($, AppRoutePaths.workBrowser(workId: missingWorkId));

      final errorStateRendered = await _waitForPageErrorState($);
      expect(
        errorStateRendered,
        isTrue,
        reason:
            'a missing post must converge to AppPageErrorState through the '
            'canonical error mapping, not a blank page or endless loading',
      );

      // 错误旅程后回到首页，壳仍健康。
      await patrolGoTo($, AppRoutePaths.home);
      await waitForHomeShell($);
      expect($(find.byKey(homeSearchChromeKey)).visible, isTrue);
    },
  );
}

Future<bool> _waitForPageErrorState(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppPageErrorState).evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
