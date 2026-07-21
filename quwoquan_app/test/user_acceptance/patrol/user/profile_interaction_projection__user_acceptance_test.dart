/// Patrol UAT：我的主页的互动页经 production Remote 读取真实投影。
///
/// 不注入 Provider、Mock、fixture 或本地 HTTP override。Gamma 中没有当前 Persona
/// 的互动记录时，空态是合法的真实响应；本用例仍要求互动 Tab 完成远端加载并收敛。
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
    'my_profile_interaction_tab_reads_remote_projection',
    tags: ['t4', 'content', 'user-profile'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance tests must run with API_CONTRACT_ENV=gamma',
      );
      await launchPatrolAppOnce($);
      await patrolGoTo($, AppRoutePaths.profile);

      await $(
        find.text(UITextConstants.profileTabInteraction),
      ).waitUntilVisible(timeout: const Duration(seconds: 20));
      await $(find.text(UITextConstants.profileTabInteraction)).tap();

      final converged = await _waitForInteractionProjection($);
      expect(
        converged,
        isTrue,
        reason:
            'interaction tab must resolve the production Remote projection rather than a fixture',
      );
    },
  );
}

Future<bool> _waitForInteractionProjection(PatrolIntegrationTester $) async {
  final expected = <Finder>[
    find.text(UITextConstants.profileInteractionEmptyLikes),
    find.text(UITextConstants.profileInteractionEmptyComments),
    find.text(UITextConstants.profileInteractionEmptyShares),
    find.text(UITextConstants.profileInteractionDirectionReceived),
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
