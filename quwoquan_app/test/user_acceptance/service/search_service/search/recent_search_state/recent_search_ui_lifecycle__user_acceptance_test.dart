// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
/// Patrol UAT：最近搜索通过 production UI 完成写入、回读、删除与清空。
///
/// 查询值由本次运行生成，避免依赖 seed 或固定业务内容。测试只操作真实页面，
/// 不读取 RecentSearch port，也不清理本地 store 来制造 Remote 证据。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_page.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _patrolSessionMode = String.fromEnvironment('QWQ_PATROL_SESSION_MODE');
const _searchFieldKey = ValueKey<String>('global_search_field');
const _submitButtonKey = ValueKey<String>('global_search_submit_visible');

void main() {
  patrolTest(
    'recent_search_ui_upsert_list_delete_clear_and_reenter',
    tags: const ['user-acceptance', 'search', 'gamma'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 20),
      printLogs: true,
    ),
    ($) async {
      assert(
        _apiContractEnv == 'gamma',
        'Search user_acceptance must run with API_CONTRACT_ENV=gamma',
      );
      assert(
        _patrolSessionMode == 'runtime_anonymous_session',
        'Recent-search mutation UAT requires a disposable anonymous account',
      );
      final runId = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
      final deleteQuery = 'qwq-uat-no-hit-delete-$runId';
      final clearQuery = 'qwq-uat-no-hit-clear-$runId';

      await launchPatrolAppOnce($);

      await _submitNoHitQuery($, deleteQuery);
      await _reenterSearchAndWaitForHistory($);
      await _expectHistoryEntry($, deleteQuery);
      await _deleteHistoryEntry($, deleteQuery);
      await _reenterSearchAndWaitForHistory($);
      expect(find.text(deleteQuery), findsNothing);

      await _submitNoHitQuery($, clearQuery);
      await _reenterSearchAndWaitForHistory($);
      await _expectHistoryEntry($, clearQuery);
      await _clearHistoryThroughUi($);
      await _reenterSearchAndWaitForHistory($);
      expect(find.text(clearQuery), findsNothing);
      expect(find.byType(AppPageErrorState), findsNothing);
    },
  );
}

Future<void> _submitNoHitQuery(PatrolIntegrationTester $, String query) async {
  await patrolGoTo($, AppRoutePaths.globalSearch);
  await $(
    find.byKey(_searchFieldKey),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  await $(find.byKey(_searchFieldKey)).enterText(query);
  await $(
    find.byKey(_submitButtonKey),
  ).waitUntilVisible(timeout: const Duration(seconds: 5));
  await $(find.byKey(_submitButtonKey)).tap();
  await $(
    find.byType(SearchNetworkResultsPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 10));

  final emptyResult = find.text(UITextConstants.searchNoResultsForQuery(query));
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    expect(
      find.byType(AppPageErrorState),
      findsNothing,
      reason: 'Search Remote failure cannot masquerade as a no-hit result',
    );
    if (emptyResult.evaluate().isNotEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  fail(
    'Unique query did not converge to the canonical no-hit terminal: $query',
  );
}

Future<void> _reenterSearchAndWaitForHistory(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.home);
  await patrolGoTo($, AppRoutePaths.globalSearch);
  await $(
    find.byKey(_searchFieldKey),
  ).waitUntilVisible(timeout: const Duration(seconds: 20));
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    if (find.byType(AppRequestFeedback).evaluate().isEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  fail('Recent search UI did not finish hydrating');
}

Future<void> _expectHistoryEntry(
  PatrolIntegrationTester $,
  String query,
) async {
  await $(
    find.text(query),
  ).waitUntilVisible(timeout: const Duration(seconds: 15));
  expect(find.byType(AppPageErrorState), findsNothing);
}

Future<void> _deleteHistoryEntry(
  PatrolIntegrationTester $,
  String query,
) async {
  await $(TestKeys.searchHistoryManageButton).tap();
  final row = find
      .ancestor(of: find.text(query), matching: find.byType(CupertinoButton))
      .first;
  final removeAction = find.descendant(
    of: row,
    matching: find.byIcon(CupertinoIcons.xmark),
  );
  await $(removeAction).waitUntilVisible(timeout: const Duration(seconds: 5));
  await $(removeAction).tap();
  await _waitForTextAbsent($, query);
}

Future<void> _clearHistoryThroughUi(PatrolIntegrationTester $) async {
  await $(TestKeys.searchHistoryManageButton).tap();
  await $(TestKeys.searchHistoryClearButton).tap();
  await $(
    find.text(SearchText.searchHistoryClearAction),
  ).waitUntilVisible(timeout: const Duration(seconds: 5));
  await $(find.text(SearchText.searchHistoryClearAction)).tap();
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (DateTime.now().isBefore(deadline)) {
    if (find.text(SearchText.searchHistoryTitle).evaluate().isEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  fail('Recent search clear action did not reach an empty history state');
}

Future<void> _waitForTextAbsent(PatrolIntegrationTester $, String value) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (DateTime.now().isBefore(deadline)) {
    if (find.text(value).evaluate().isEmpty) {
      return;
    }
    await $.pump(const Duration(milliseconds: 250));
  }
  fail('Expected text to disappear after UI mutation: $value');
}
