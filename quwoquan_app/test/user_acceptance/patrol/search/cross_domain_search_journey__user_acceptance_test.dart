// spec_ref: specs/feature-tree/spec.md#uat-001
// spec_ref: specs/feature-tree/global-search-experience/spec.md#dom-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
/// user_acceptance Patrol：全局搜索真实 Gamma 旅程。
///
/// 本用例启动真实 App 与 production Remote composition，不注入 Mock、fixture
/// 或数据源模式。它验证本地契约测试无法替代的 App → Gamma search-service 链路：
/// 输入查询、进入固定结果 Tab、渲染真实 ES 命中。
///
/// 本地执行（iOS Simulator 可直接访问宿主 127.0.0.1）：
///   patrol test --target \
///     test/user_acceptance/patrol/search/cross_domain_search_journey__user_acceptance_test.dart \
///     -d `<device-id>` \
///     --dart-define=APP_RUNTIME_ENV=gamma \
///     --dart-define=API_CONTRACT_ENV=gamma \
///     --dart-define=RUN_T4_PATROL=true \
///     --dart-define=QWQ_PATROL_SESSION_MODE=gamma_local_anonymous_runtime \
///     --dart-define=CLOUD_GATEWAY_BASE_URL=https://api.gamma.quwoquan.com:19000
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/services/search_recent_history_store.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _query = '西湖';
const _expectedResultTitle = '西湖晨光摄影测试详情';
const _searchFieldKey = ValueKey<String>('global_search_field');
const _submitButtonKey = ValueKey<String>('global_search_submit_visible');
const _allResultsKey = ValueKey<String>('network_results_all');

void main() {
  patrolTest(
    'cross_domain_search_remote_journey',
    tags: ['t4', 'search', 'gamma'],
    skip: !kRunPatrolT4,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);
      assert(
        _apiContractEnv == 'gamma',
        'Search user_acceptance must run with API_CONTRACT_ENV=gamma',
      );

      await patrolGoTo($, AppRoutePaths.globalSearch);
      final searchFieldVisible = await _waitForFinder(
        $,
        find.byKey(_searchFieldKey),
        timeout: const Duration(seconds: 20),
      );
      expect(searchFieldVisible, isTrue, reason: '全局搜索输入框必须可达');

      await $(find.byKey(_searchFieldKey)).enterText(_query);
      final submitVisible = await _waitForFinder(
        $,
        find.byKey(_submitButtonKey),
        timeout: const Duration(seconds: 5),
      );
      expect(submitVisible, isTrue, reason: '输入查询后必须显示搜索动作');
      await $(find.byKey(_submitButtonKey)).tap();

      final resultsRouteVisible = await _waitForFinder(
        $,
        find.byType(SearchNetworkResultsPage),
        timeout: const Duration(seconds: 8),
      );
      expect(resultsRouteVisible, isTrue, reason: '提交查询后必须进入网络结果页');
      final resultsVisible = await _waitForFinder(
        $,
        find.byKey(_allResultsKey),
        timeout: const Duration(seconds: 30),
      );
      expect(resultsVisible, isTrue, reason: '真实 Gamma 查询必须进入全部结果流');
      for (final tabLabel in <String>[
        SearchText.searchXiaoquTab,
        SearchText.searchAllTab,
        SearchText.searchIntersectionTab,
        SearchText.searchImageTab,
        SearchText.searchVideoTab,
        SearchText.searchArticleTab,
      ]) {
        expect(find.text(tabLabel).evaluate(), isNotEmpty, reason: tabLabel);
      }

      final remoteHitVisible = await _waitForFinder(
        $,
        find.textContaining(_expectedResultTitle),
        timeout: const Duration(seconds: 30),
      );
      expect(
        remoteHitVisible,
        isTrue,
        reason: '结果页必须渲染 Gamma ES 中的真实西湖内容，不得使用端侧假数据',
      );

      // 有效行动漏斗必须由同一条真实 Remote 结果链产生：先保持超过
      // 3 秒以满足 qualified dwell，再点击命中，让页面的 dispose 路径提交
      // dwell feedback，同时由卡片点击提交 click feedback。
      await $.pump(const Duration(seconds: 3));
      await $(find.textContaining(_expectedResultTitle)).tap();
      await $.pump(const Duration(seconds: 1));

      // 等待提交路径完成 RecentSearchState 远端 upsert，再销毁当前页面状态并
      // 清空本地表现层缓存。随后只能由 Remote hydrate 重新显示该查询。
      await $.pump(const Duration(seconds: 2));
      await patrolGoTo($, AppRoutePaths.home);
      await SearchRecentHistoryStore.clearAllNamespaces();
      await patrolGoTo($, AppRoutePaths.globalSearch);
      final recentSearchVisible = await _waitForFinder(
        $,
        find.text(_query),
        timeout: const Duration(seconds: 15),
      );
      expect(
        recentSearchVisible,
        isTrue,
        reason: '匿名登录态清空本地缓存后必须从 Remote RecentSearchState 回显最近搜索',
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
