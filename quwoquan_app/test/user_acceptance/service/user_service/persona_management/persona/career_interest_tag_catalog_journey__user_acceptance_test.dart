// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-001
/// user_acceptance Patrol：职业与兴趣页读取真实 Gamma 标签目录。
///
/// 用例启动 production Remote composition 与真实匿名登录会话，不注入 Mock。
/// 「风光影像」是 control-plane taxonomy 的叶子标签；页面出现该文案证明
/// ProfileEditSnapshot 与 tag-service ListTagChildren 均通过真实网关完成。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/career_interest_page.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _expectedRemoteLeafLabel = '风光影像';

void main() {
  patrolTest(
    'career_interest_reads_remote_tag_catalog',
    tags: ['user-acceptance', 'tag', 'gamma', 'user-profile'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      assert(
        _apiContractEnv == 'gamma',
        'Tag user_acceptance must run with API_CONTRACT_ENV=gamma',
      );

      await patrolGoTo($, AppRoutePaths.profileCareerInterests);
      final pageVisible = await _waitForFinder(
        $,
        find.byType(CareerInterestPage),
        timeout: const Duration(seconds: 20),
      );
      expect(pageVisible, isTrue, reason: '职业与兴趣页必须可达');
      expect(
        find.text(ProfileText.careerInterestOccupationSection).evaluate(),
        isNotEmpty,
        reason: 'ProfileEditSnapshot 与标签目录加载后必须进入正常内容态',
      );

      final remoteLeafVisible = await _waitForFinder(
        $,
        find.text(_expectedRemoteLeafLabel),
        timeout: const Duration(seconds: 30),
      );
      expect(
        remoteLeafVisible,
        isTrue,
        reason: '页面必须渲染 Gamma tag-service 返回的 canonical taxonomy 叶子',
      );
    },
  );
}

Future<bool> _waitForFinder(
  PatrolIntegrationTester $,
  Finder finder, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (finder.evaluate().isNotEmpty) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
