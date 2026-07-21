/// Patrol UAT：当前 Persona 的举报生命周期由 production Remote 读取。
///
/// 该测试故意不注入 Query/Mock；Gamma seed 或前置真实举报均可作为数据来源。
/// 通过条件是页面从真实 `ListMyReports` 响应收敛为私有空态或一个公开生命周期状态，
/// 而不是只验证路由或固定 fixture。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

void main() {
  patrolTest(
    'my_reports_page_remote_lifecycle_converges',
    tags: ['t4', 'content', 'report'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.myReports);

      await $(
        find.text(UITextConstants.myReportsTitle),
      ).waitUntilVisible(timeout: const Duration(seconds: 15));

      final converged = await _waitForRemoteLifecycleState($);
      expect(
        converged,
        isTrue,
        reason:
            'MyReports must finish a production Remote query as empty or a public lifecycle state',
      );
    },
  );
}

Future<bool> _waitForRemoteLifecycleState(PatrolIntegrationTester $) async {
  final expected = <Finder>[
    find.text(UITextConstants.myReportsEmptyTitle),
    find.text(UITextConstants.reportStatusPending),
    find.text(UITextConstants.reportStatusReviewing),
    find.text(UITextConstants.reportStatusResolved),
    find.text(UITextConstants.reportStatusDismissed),
  ];
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (expected.any((finder) => finder.evaluate().isNotEmpty)) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
