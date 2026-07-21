/// user_acceptance Patrol: 用户主页核心旅程（用户主页商用化收口 R-UPROF-004）
///
/// 对应 AppRoot Journey：profile-private-activity-history 与
/// content-discovery-to-consumption 的 content-detail-profile-handoff。
/// 本用例在真实设备 + 真实 gamma 后端上守护 flutter_test 无法替代的端到端行为：
/// 底栏进入我的主页真实 bundle 渲染、编辑资料入口可达、feed 作者头像进入他人
/// 主页后的真实关注/取关往返。
///
/// 与 local_contract 的映射（R12 一体性）：
///   - 主页壳层骨架/统计行/操作条渲染   <- profile_shell_widget__local_contract_test
///   - 关注乐观态与 outbox 对账          <- persona_relationship_block_facets__local_contract_test
///   - 编辑资料表单与保存                <- edit_profile 页 local_contract 组
///   - 粉丝/关注统计详情                 <- profile_stats_page__local_contract_test
///
/// 执行方式（本地，emulator 访问宿主用 10.0.2.2）：
///   patrol test --target test/user_acceptance/patrol/user/profile_journey__user_acceptance_test.dart \
///     -d emulator-5554 \
///     --dart-define=APP_RUNTIME_ENV=gamma --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:19000 \
///     --dart-define=API_CONTRACT_BASE_URL=http://10.0.2.2:19000 \
///     --dart-define=MEDIA_IMAGE_CDN_BASE_URL=http://10.0.2.2:19100 \
///     --dart-define=MEDIA_VIDEO_CDN_BASE_URL=http://10.0.2.2:19100 \
///     --dart-define=APP_CURRENT_USER_ID=us_01_3278_01kvevr8s7s3b0arr7x3p27efe \
///     --dart-define=TEST_AUTH_TOKEN=local-patrol-token
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);

const _kHomeSearchChrome = ValueKey<String>('home-search-chrome');
const _kFeedCard0 = ValueKey<String>('home-feed-card-0');
const _kRelationHeader = ValueKey<String>('home-relation-card-header');
const _kEditProfileNicknameRow = ValueKey<String>('edit-profile-nickname-row');
const _kEditProfileTextSave = ValueKey<String>('edit-profile-text-save');
const _kEditProfileSave = ValueKey<String>('edit-profile-save');

// 用户主页壳层可命中骨架 key（profile_shell / profile_header 真相源）。
const _kProfileKeys = <ValueKey<String>>[
  ValueKey<String>('profile-header-avatar'),
  ValueKey<String>('profile-shell-summary-card'),
];

void main() {
  patrolTest(
    'user_profile_my_page_renders_with_edit_entry',
    tags: ['t4', 'user-profile', 'user'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      assert(
        _apiContractEnv == 'gamma',
        'Patrol user_acceptance journey must run with API_CONTRACT_ENV=gamma',
      );
      await _recoverToHomeFeed($);

      // 底栏「我」进入我的主页：真实 homepage-bundle 渲染壳层骨架。
      final tappedProfileTab = await _tapBottomProfileTab($);
      expect(tappedProfileTab, isTrue, reason: '应能点击底栏「我」进入我的主页');
      final reachedProfile = await _waitForAnyKeyInTree(
        $,
        _kProfileKeys,
        timeout: const Duration(seconds: 20),
      );
      expect(
        reachedProfile,
        isTrue,
        reason: '我的主页必须渲染壳层骨架（头像/身份卡，真实 bundle 非空态）',
      );

      // 编辑资料真实保存并回读：入口、字段编辑、远端写入及主页刷新缺一不可。
      final editEntry = find.text(UITextConstants.profileEditLabel);
      expect(editEntry.evaluate(), isNotEmpty, reason: '我的主页必须提供编辑资料入口');
      await $.tester.tap(editEntry.first);
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));
      final reachedEdit = await _waitForFinderInTree(
        $,
        find.text(UITextConstants.editProfileSaveAction),
        timeout: const Duration(seconds: 12),
      );
      expect(reachedEdit, isTrue, reason: '编辑资料页应可从我的主页进入');
      await _editNicknameAndVerifyProfileRefresh($);
    },
  );

  patrolTest(
    'user_profile_other_page_follow_roundtrip',
    tags: ['t4', 'user-profile', 'user'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      await _recoverToHomeFeed($);

      // feed 首卡作者头像进入他人主页（对象跳转链路）。
      final navigated = await _tapFirstAuthorAvatar($);
      expect(navigated, isTrue, reason: '应能点击 feed 首卡作者头像');
      await $.pump(const Duration(milliseconds: 400));
      await $.pump(const Duration(seconds: 1));
      final reachedProfile = await _waitForAnyKeyInTree(
        $,
        _kProfileKeys,
        timeout: const Duration(seconds: 15),
      );
      expect(reachedProfile, isTrue, reason: '作者头像应跳转到用户主页');

      // 关注/取关真实往返：无论 seed 初态如何，都先归一为未关注，再验证完整往返。
      final followEntry = find.text(UITextConstants.follow);
      final followingEntry = find.text(UITextConstants.following);
      expect(
        followEntry.evaluate().isNotEmpty ||
            followingEntry.evaluate().isNotEmpty,
        isTrue,
        reason: '他人主页必须提供关注/已关注语义入口',
      );
      if (followingEntry.evaluate().isNotEmpty) {
        await $.tester.tap(followingEntry.first);
        await $.pump(const Duration(milliseconds: 600));
        final normalized = await _waitForFinderInTree(
          $,
          followEntry,
          timeout: const Duration(seconds: 10),
        );
        expect(normalized, isTrue, reason: '既有已关注态必须可先取关并回到未关注态');
      }

      await $.tester.tap(followEntry.first);
      await $.pump(const Duration(milliseconds: 400));
      final followed = await _waitForFinderInTree(
        $,
        followingEntry,
        timeout: const Duration(seconds: 10),
      );
      expect(followed, isTrue, reason: '点击关注后应进入已关注态（真实远端写入 + 乐观态）');

      await $.tester.tap(followingEntry.first);
      await $.pump(const Duration(milliseconds: 600));
      final unfollowed = await _waitForFinderInTree(
        $,
        followEntry,
        timeout: const Duration(seconds: 10),
      );
      expect(unfollowed, isTrue, reason: '取关后应回到可关注态（状态往返无脏残留）');

      await patrolGoTo($, AppRoutePaths.home);
    },
  );
}

// ───────────────────────── helpers ─────────────────────────

Future<void> _editNicknameAndVerifyProfileRefresh(
  PatrolIntegrationTester $,
) async {
  final updatedNickname =
      'gamma${DateTime.now().millisecondsSinceEpoch % 1000000000}';
  final nicknameRow = find.byKey(_kEditProfileNicknameRow);
  expect(nicknameRow.evaluate(), isNotEmpty, reason: '编辑资料页必须提供昵称编辑项');
  await $.tester.tap(nicknameRow.first);
  await $.pump(const Duration(milliseconds: 300));

  final textField = find.byType(CupertinoTextField);
  final reachedTextEditor = await _waitForFinderInTree(
    $,
    textField,
    timeout: const Duration(seconds: 10),
  );
  expect(reachedTextEditor, isTrue, reason: '昵称编辑页必须加载可编辑文本框');
  await $.tester.enterText(textField.first, updatedNickname);
  await $.tester.tap(find.byKey(_kEditProfileTextSave));
  await $.pump(const Duration(milliseconds: 300));

  final profileSave = find.byKey(_kEditProfileSave);
  final returnedToEditProfile = await _waitForFinderInTree(
    $,
    profileSave,
    timeout: const Duration(seconds: 10),
  );
  expect(returnedToEditProfile, isTrue, reason: '昵称编辑保存后必须返回编辑资料页');
  await $.tester.tap(profileSave);

  final refreshedProfile = await _waitForFinderInTree(
    $,
    find.text(updatedNickname),
    timeout: const Duration(seconds: 15),
  );
  expect(refreshedProfile, isTrue, reason: '资料保存后主页必须回读远端昵称，不能只停留在本地编辑态');
}

Future<bool> _waitForKeyInTree(
  PatrolIntegrationTester $,
  Key key, {
  required Duration timeout,
}) {
  return _waitForFinderInTree($, find.byKey(key), timeout: timeout);
}

Future<bool> _waitForAnyKeyInTree(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final key in keys) {
      if (find.byKey(key).evaluate().isNotEmpty) {
        return true;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}

Future<bool> _waitForFinderInTree(
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

/// 与 home_recommendation_journey 同一恢复约定：等待首页壳层就绪后再操作，
/// 避免在首页根 route 上按返回导致 Activity finish。
Future<void> _recoverToHomeFeed(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.home);
  await _waitForKeyInTree(
    $,
    _kHomeSearchChrome,
    timeout: const Duration(seconds: 30),
  );
  await $.pump(const Duration(milliseconds: 500));
  await _waitForKeyInTree($, _kFeedCard0, timeout: const Duration(seconds: 60));
}

/// 底栏「我」tab：登录态文本为 AppConceptConstants.profile（'我'），
/// 游客态为 bottomNavGuestProfile。两者都尝试命中。
Future<bool> _tapBottomProfileTab(PatrolIntegrationTester $) async {
  for (final label in <String>[
    AppConceptConstants.profile,
    UITextConstants.bottomNavGuestProfile,
  ]) {
    final finder = find.text(label);
    if (finder.evaluate().isNotEmpty) {
      await $.tester.tap(finder.last);
      await $.pump(const Duration(milliseconds: 600));
      return true;
    }
  }
  return false;
}

Future<bool> _tapFirstAuthorAvatar(PatrolIntegrationTester $) async {
  final header = find.byKey(_kRelationHeader);
  if (header.evaluate().isEmpty) {
    return false;
  }
  final avatar = find.descendant(
    of: header.first,
    matching: find.byType(CupertinoButton),
  );
  if (avatar.evaluate().isEmpty) {
    return false;
  }
  await $.tester.ensureVisible(avatar.first);
  await $.pump(const Duration(milliseconds: 200));
  await $.tester.tap(avatar.first);
  await $.pump(const Duration(milliseconds: 300));
  return true;
}
