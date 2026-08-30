// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
/// user_acceptance Patrol: 用户主页核心旅程（用户主页商用化收口 R-UPROF-004）
///
/// 对应 AppRoot Journey：profile-private-activity-history 与
/// content-discovery-to-consumption 的 content-detail-profile-handoff。
/// 本用例在真实设备 + 当前 alpha/beta/gamma 后端上守护 flutter_test 无法替代的端到端行为：
/// 三环境 P0 覆盖我的主页身份/Tab/终态，以及 feed 作者头像、作品与作者主页终态；
/// Gamma P1 继续覆盖交集资产面、编辑资料保存回读与真实关注/取关往返。
///
/// 与 local_contract 的映射（R12 一体性）：
///   - 主页壳层骨架/统计行/操作条渲染   <- profile_shell_widget__local_contract_test
///   - 关注乐观态与 outbox 对账          <- persona_relationship_block_facets__local_contract_test
///   - 编辑资料表单与保存                <- edit_profile 页 local_contract 组
///   - 粉丝/关注统计详情                 <- profile_stats_page__local_contract_test
///   - 交集资产面（REQ-008 四模块）      <- my_gatherings_page/_entry_card、
///     my_experience_asset_card、creator_flywheel_proof_row、
///     intersection_actionable_reasons 各 local_contract 组
///
/// 执行方式：由 `run_environment_patrol_smoke.py` 消费所选 target topology
/// 投影全部 canonical HTTPS/WSS endpoint，并在 Android 上安装 target 端口的
/// `adb reverse`。禁止手工注入 HTTP 或私有 IP URL。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart'
    show appImageLoadErrorKey, appImageLoadSuccessKey;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/intersection_statement_row.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../support/runtime/patrol/patrol_app_content_screenshot.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_entry_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/author_impact_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/author_impact_evidence.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/creator_flywheel_proof_row.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_experience_asset_card.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_card.dart';

const _apiContractEnv = String.fromEnvironment('API_CONTRACT_ENV');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _appContentProfileP0Only = bool.fromEnvironment(
  'APP_CONTENT_PROFILE_P0_ONLY',
);

const _kHomeSearchChrome = ValueKey<String>('home-primary-tab-chrome');
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
const _kProfilePrimaryTabKeys = <ValueKey<String>>[
  ValueKey<String>('profile-shell-primary-tabs-inline'),
  ValueKey<String>('profile-shell-primary-tabs-pinned'),
];

bool get _runsGammaProfileP1 =>
    _apiContractEnv == 'gamma' && !_appContentProfileP0Only;

void main() {
  patrolTest(
    'user_profile_my_page_renders_with_edit_entry',
    tags: ['user-acceptance', 'user-profile', 'user'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      _expectSelectedNonProdEnvironment();
      await _recoverToHomeFeed($);

      // 底栏「我」进入我的主页：真实 homepage-bundle 渲染壳层骨架。
      final tappedProfileTab = await _tapBottomProfileTab($);
      expect(tappedProfileTab, isTrue, reason: '应能点击底栏「我」进入我的主页');
      for (final identityKey in _kProfileKeys) {
        final identityMounted = await _waitForKeyInTree(
          $,
          identityKey,
          timeout: const Duration(seconds: 20),
        );
        expect(
          identityMounted,
          isTrue,
          reason: '我的主页必须渲染头像与身份摘要（真实 bundle 非空态）',
        );
      }
      final primaryTabsMounted = await _waitForAnyKeyInTree(
        $,
        _kProfilePrimaryTabKeys,
        timeout: const Duration(seconds: 20),
      );
      expect(primaryTabsMounted, isTrue, reason: '我的主页必须渲染 canonical 一级 Tab');
      final terminalProfile = find.byKey(_kProfileKeys.first);
      expect(
        GoRouterState.of($.tester.element(terminalProfile.first)).uri.path,
        AppRoutePaths.profile,
        reason: '我的主页 P0 终态必须保持在 profile route',
      );

      // Gamma P1 保留额外投影与写交互；Alpha/Beta 精简 P0 不执行这些 mutation。
      if (_runsGammaProfileP1) {
        await _verifyAuthorImpactEvidence($);
        await _verifyIntersectionAssetSurfaces($);

        // 编辑资料真实保存并回读：入口、字段编辑、远端写入及主页刷新缺一不可。
        final editEntry = find.text(ProfileText.profileEditLabel);
        expect(editEntry.evaluate(), isNotEmpty, reason: '我的主页必须提供编辑资料入口');
        await $.tester.tap(editEntry.first);
        await $.pump(const Duration(milliseconds: 400));
        await $.pump(const Duration(seconds: 1));
        final reachedEdit = await _waitForFinderInTree(
          $,
          find.text(ProfileText.editProfileSaveAction),
          timeout: const Duration(seconds: 12),
        );
        expect(reachedEdit, isTrue, reason: '编辑资料页应可从我的主页进入');
        await _editNicknameAndVerifyProfileRefresh($);
      }
    },
  );

  patrolTest(
    'user_profile_other_page_follow_roundtrip',
    tags: ['user-acceptance', 'user-profile', 'user'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchPatrolAppOnce($);
      _expectSelectedNonProdEnvironment();
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

      const profileAvatarImageKey = ValueKey<String>(
        'profile-header-avatar-image',
      );
      final profileAvatar = find.byKey(profileAvatarImageKey);
      final avatarMounted = await _waitForFinderInTree(
        $,
        profileAvatar,
        timeout: const Duration(seconds: 15),
      );
      expect(avatarMounted, isTrue, reason: 'release 作者主页必须挂载真实头像媒体');
      final avatarDecoded = await _waitForFinderInTree(
        $,
        find.descendant(
          of: profileAvatar,
          matching: find.byKey(appImageLoadSuccessKey),
        ),
        timeout: const Duration(seconds: 20),
      );
      expect(avatarDecoded, isTrue, reason: 'release 作者头像必须真实解码成功');
      expect(
        find
            .descendant(
              of: profileAvatar,
              matching: find.byKey(appImageLoadErrorKey),
            )
            .evaluate(),
        isEmpty,
        reason: 'release 作者头像不得停留在显式加载失败态',
      );

      // 记录 tab（默认二级容器）：feed 作者必有已发布作品，ListUserPosts 真实
      // wire 必须能被 generated decoder 解码并渲染作品网格。回归背景：契约
      // 漂移曾让有作品作者的主页整页解码失败，同时显示「共有 0 条记录」+
      // 「内容暂时无法显示」的矛盾组合。
      final worksGridRendered = await _waitForKeyInTree(
        $,
        const ValueKey<String>('profile-works-grid'),
        timeout: const Duration(seconds: 20),
      );
      expect(
        worksGridRendered,
        isTrue,
        reason: 'feed 作者主页「记录」必须渲染作品网格（ListUserPosts 可解码且非空）',
      );
      expect(
        find.text(SearchText.recoveryInvalidContentTitle).evaluate(),
        isEmpty,
        reason: '「记录」列表不得进入「内容暂时无法显示」契约错误态',
      );
      expect(
        find.text(UITextConstants.profileRecordsTotal(0)).evaluate(),
        isEmpty,
        reason: '有作品作者不得显示「共有 0 条记录」伪空态',
      );

      final p0TerminalKey = _kProfileKeys.firstWhere(
        (key) => find.byKey(key).evaluate().isNotEmpty,
      );
      final p0TerminalProfile = find.byKey(p0TerminalKey);
      final p0TerminalRoute = GoRouterState.of(
        $.tester.element(p0TerminalProfile.first),
      ).uri.path;
      expect(
        p0TerminalRoute,
        startsWith(AppRoutePaths.userProfilePathTemplate.split('{').first),
        reason: '作者主页 P0 终态必须保持在 author profile route',
      );

      if (!_runsGammaProfileP1) {
        await emitPatrolAppContentPageScreenshotReady(
          $,
          environment: _apiContractEnv,
          suite: 'profile-journey',
          route: p0TerminalRoute,
          terminalKey: p0TerminalKey.value,
          terminalFinder: p0TerminalProfile,
        );
        return;
      }

      // 关注/取关真实往返：无论 seed 初态如何，都先归一为未关注，再验证完整往返。
      final followEntry = find.text(FoundationText.follow);
      final followingEntry = find.text(FoundationText.following);
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
      final terminalKey = _kProfileKeys.firstWhere(
        (key) => find.byKey(key).evaluate().isNotEmpty,
      );
      final terminalProfile = find.byKey(terminalKey);
      final terminalRoute = GoRouterState.of(
        $.tester.element(terminalProfile.first),
      ).uri.path;
      expect(
        terminalRoute,
        startsWith(AppRoutePaths.userProfilePathTemplate.split('{').first),
        reason: 'profile screenshot terminal must remain on an author profile',
      );
      await emitPatrolAppContentPageScreenshotReady(
        $,
        environment: _apiContractEnv,
        suite: 'profile-journey',
        route: terminalRoute,
        terminalKey: terminalKey.value,
        terminalFinder: terminalProfile,
      );
    },
  );
}

Future<void> _verifyAuthorImpactEvidence(PatrolIntegrationTester $) async {
  final card = find.byKey(AuthorImpactCard.cardKey);
  final reachedCard = await _waitForFinderInTree(
    $,
    card,
    timeout: const Duration(seconds: 20),
  );
  expect(
    reachedCard,
    isTrue,
    reason: '我的主页必须回读并展示 $_apiContractEnv AuthorImpact 摘要',
  );

  final statement = find.descendant(
    of: card.first,
    matching: find.byType(IntersectionStatementRow),
  );
  final reachedStatement = await _waitForFinderInTree(
    $,
    statement,
    timeout: const Duration(seconds: 15),
  );
  expect(
    reachedStatement,
    isTrue,
    reason: '$_apiContractEnv AuthorImpact 摘要必须包含可下钻的权威事实',
  );
  await $.tester.ensureVisible(statement.first);
  await $.tester.tap(statement.first);
  await $.pump(const Duration(milliseconds: 400));

  final reachedSheet = await _waitForFinderInTree(
    $,
    find.byType(AuthorImpactEvidenceSheet),
    timeout: const Duration(seconds: 12),
  );
  expect(reachedSheet, isTrue, reason: '点击影响力事实必须打开证据明细');
  final reachedEvidence = await _waitForFinderInTree(
    $,
    find.text(DiscoveryFeedText.impactEvidenceSheetDetailLabel),
    timeout: const Duration(seconds: 15),
  );
  expect(reachedEvidence, isTrue, reason: '证据明细必须回读服务端 evidence，而非样本或空态');
  await $.tester.tap(find.text(FoundationText.confirm));
  await $.pump(const Duration(milliseconds: 300));
}

/// 交集资产面（REQ-008 / SIT-008 user_acceptance 层）：
/// 我的交集卡与「我的行动」入口在 mine 模式恒渲染；共同经历/成行力按真实
/// 数据条件渲染（无数据必须诚实不渲染，禁止占位空态冒充）。「我的行动」
/// 入口点击进入分组页并回读真实 ByHost 公开读面。
Future<void> _verifyIntersectionAssetSurfaces(PatrolIntegrationTester $) async {
  // 我的交集收件箱卡：mine 恒渲染（真实 summary + 事实交集预览或诚实空态）。
  final inboxCard = find.byKey(MyIntersectionInboxCard.cardKey);
  final reachedInbox = await _waitForFinderInTree(
    $,
    inboxCard,
    timeout: const Duration(seconds: 20),
  );
  expect(reachedInbox, isTrue, reason: '我的主页必须渲染「我的交集」收件箱卡');

  // 「我的行动」单行入口：恒渲染；点击进入分组页回读 ByHost 公开读面。
  final gatheringsEntry = find.byKey(MyGatheringsEntryCard.cardKey);
  final reachedEntry = await _waitForFinderInTree(
    $,
    gatheringsEntry,
    timeout: const Duration(seconds: 15),
  );
  expect(reachedEntry, isTrue, reason: '我的主页必须渲染「我的行动」单行入口');
  await $.tester.ensureVisible(gatheringsEntry.first);
  await $.pump(const Duration(milliseconds: 200));
  await $.tester.tap(gatheringsEntry.first);
  await $.pump(const Duration(milliseconds: 400));
  final reachedSegments = await _waitForFinderInTree(
    $,
    find.text(GatheringText.myGatheringsSegmentUpcoming),
    timeout: const Duration(seconds: 12),
  );
  expect(reachedSegments, isTrue, reason: '我的行动分组页必须渲染三分组（即将开始/已结束/已取消）而非错误态');
  expect(
    find.text(GatheringText.myGatheringsSegmentCancelled).evaluate(),
    isNotEmpty,
    reason: '分组闭集必须完整（已取消分组可达）',
  );
  await patrolGoTo($, AppRoutePaths.profile);
  final backToProfile = await _waitForAnyKeyInTree(
    $,
    _kProfileKeys,
    timeout: const Duration(seconds: 15),
  );
  expect(backToProfile, isTrue, reason: '离开我的行动分组页后必须能回到我的主页');

  // 共同经历资产卡：诚实两分支——渲染则必须带标题与主句行；未渲染时不得
  // 出现任何「暂无经历」式占位（REQ-008：诚实空态=不渲染）。
  final experienceCard = find.byKey(MyExperienceAssetCard.cardKey);
  if (experienceCard.evaluate().isNotEmpty) {
    expect(
      find.text(DiscoveryFeedText.myExperienceTitle).evaluate(),
      isNotEmpty,
      reason: '共同经历资产卡渲染时必须带标题（云侧经历交集事实直出）',
    );
  } else {
    expect(
      find.text(DiscoveryFeedText.myExperienceTitle).evaluate(),
      isEmpty,
      reason: '无经历交集时不得渲染共同经历占位（诚实空态=不渲染）',
    );
  }

  // 成行力行：诚实两分支——零成形或读取失败不渲染，渲染则为事实计数行。
  final proofRow = find.byKey(CreatorFlywheelProofRow.rowKey);
  if (proofRow.evaluate().isNotEmpty) {
    expect(
      find.textContaining('促成').evaluate(),
      isNotEmpty,
      reason: '成行力行渲染时必须是 creator 锚点事实计数（促成 N 次同行）',
    );
  } else {
    expect(
      find.textContaining('促成').evaluate(),
      isEmpty,
      reason: '成行力行未渲染时不得残留事实计数占位（诚实空态=不渲染）',
    );
  }
}

// ───────────────────────── helpers ─────────────────────────

Future<void> _editNicknameAndVerifyProfileRefresh(
  PatrolIntegrationTester $,
) async {
  final updatedNickname =
      '$_apiContractEnv${DateTime.now().millisecondsSinceEpoch % 1000000000}';
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

void _expectSelectedNonProdEnvironment() {
  expect(
    _apiContractEnv,
    anyOf('alpha', 'beta', 'gamma'),
    reason: 'profile P0 only accepts alpha/beta/gamma',
  );
  expect(
    _appRuntimeEnv,
    _apiContractEnv,
    reason: 'APP_RUNTIME_ENV and API_CONTRACT_ENV must name the same target',
  );
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
    FoundationText.bottomNavGuestProfile,
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
