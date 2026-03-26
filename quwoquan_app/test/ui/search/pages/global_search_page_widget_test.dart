import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

GoRouter _buildRouter({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
}) {
  return GoRouter(
    initialLocation: AppRoutePaths.globalSearch,
    routes: [
      GoRoute(
        path: AppRoutePaths.globalSearch,
        builder: (context, state) {
          final effectiveLaunchContext = state.extra is SearchLaunchContext
              ? state.extra! as SearchLaunchContext
              : launchContext;
          return GlobalSearchPage(launchContext: effectiveLaunchContext);
        },
      ),
      GoRoute(
        path: AppRoutePaths.globalSearchNetworkResultsPathTemplate,
        builder: (context, state) {
          final extraContext = state.extra is SearchLaunchContext
              ? state.extra! as SearchLaunchContext
              : launchContext;
          final query = state.uri.queryParameters['query'] ?? '';
          final tab = state.uri.queryParameters['tab'];
          return SearchNetworkResultsPage(
            launchContext: extraContext.copyWith(
              prefilledQuery: query,
              initialNetworkTabId: tab,
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          return Text('chat:${state.pathParameters['id']}');
        },
      ),
      GoRoute(
        path: AppRoutePaths.circleDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          return Text('circle:${state.pathParameters['id']}');
        },
      ),
    ],
  );
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
}) {
  return ProviderScope(
    child: MaterialApp.router(
      routerConfig: _buildRouter(launchContext: launchContext),
    ),
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await const MockUserProfileRepository().clearRecentSearches();
  });

  testWidgets('无历史记录时隐藏最近搜索区块', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('最近在搜'), findsNothing);
    expect(find.byKey(TestKeys.searchHistoryManageButton), findsNothing);
  });

  testWidgets('内容选择行可打开弹窗并回写摘要', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.searchContentSelectorButton), findsOneWidget);
    expect(find.byKey(TestKeys.globalSearchScopeRail), findsOneWidget);
    expect(find.byKey(TestKeys.searchScopeAllChip), findsOneWidget);
    expect(find.byKey(TestKeys.searchScopeContactsChip), findsOneWidget);
    expect(find.byKey(TestKeys.searchScopeDirectChatChip), findsOneWidget);
    expect(find.byKey(TestKeys.searchScopeGroupChatChip), findsOneWidget);
    expect(find.byKey(TestKeys.searchScopeCirclesChip), findsOneWidget);

    final allChipText = tester.widget<Text>(
      find.descendant(
        of: find.byKey(TestKeys.searchScopeAllChip),
        matching: find.text('全部'),
      ),
    );
    expect(allChipText.style?.color, AppColors.primaryColor);

    expect(find.text('全部内容'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.searchContentSelectorButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.searchContentSheet), findsOneWidget);
    expect(find.byKey(TestKeys.searchContentArticleToggle), findsOneWidget);
    expect(find.byKey(TestKeys.searchContentImageToggle), findsOneWidget);
    expect(find.byKey(TestKeys.searchContentVideoToggle), findsOneWidget);
    expect(find.byKey(TestKeys.searchContentMomentToggle), findsOneWidget);

    await tester.tap(find.text('图片').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('视频').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('动态').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.searchContentSheetDoneButton));
    await tester.pumpAndSettle();

    expect(find.text('文章'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.searchContentSelectorButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.searchContentSheetResetButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.searchContentSheetDoneButton));
    await tester.pumpAndSettle();

    expect(find.text('全部内容'), findsOneWidget);
  });

  testWidgets('最近搜索默认折叠三行并可进入删除态删除单条记录', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'global_search_recent_entries_v1': jsonEncode(<Map<String, dynamic>>[
        _historyEntry('摄影圈'),
        _historyEntry('旅行手账'),
        _historyEntry('李明'),
        _historyEntry('周末登山'),
        _historyEntry('咖啡俱乐部'),
        _historyEntry('夜景延时'),
        _historyEntry('圈子搭子'),
      ]),
    });

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('最近在搜'), findsOneWidget);
    expect(find.byKey(TestKeys.searchHistoryExpandButton), findsOneWidget);
    expect(find.text('圈子搭子'), findsNothing);

    await tester.tap(find.byKey(TestKeys.searchHistoryManageButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.searchHistoryClearButton), findsOneWidget);
    expect(find.byKey(TestKeys.searchHistoryDoneButton), findsOneWidget);
    expect(find.text('摄影圈'), findsOneWidget);
    expect(find.text('圈子搭子'), findsOneWidget);

    final doneText = tester.widget<Text>(
      find.descendant(
        of: find.byKey(TestKeys.searchHistoryDoneButton),
        matching: find.text('完成'),
      ),
    );
    expect(doneText.style?.color, AppColors.primaryColor);

    await tester.tap(find.byIcon(CupertinoIcons.xmark).first);
    await tester.pumpAndSettle();

    expect(find.text('摄影圈'), findsNothing);
  });

  testWidgets('删除态清空前需要确认', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'global_search_recent_entries_v1': jsonEncode(<Map<String, dynamic>>[
        _historyEntry('摄影圈'),
        _historyEntry('旅行手账'),
      ]),
    });

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.searchHistoryManageButton));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.searchHistoryClearButton));
    await tester.pumpAndSettle();

    expect(find.text('清空最近搜索'), findsOneWidget);
    expect(find.text('将移除全部最近搜索记录，且无法恢复。'), findsOneWidget);

    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();

    expect(find.text('最近在搜'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.searchHistoryClearButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('清空').last);
    await tester.pumpAndSettle();

    expect(find.text('最近在搜'), findsNothing);
  });

  testWidgets('指定搜索对象可切换到联系人并过滤联想区块', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.searchScopeContactsChip));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '李',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('更多联系人'), findsOneWidget);
    expect(find.text('更多聊天记录'), findsNothing);
  });

  testWidgets('指定搜索对象可切换到群聊', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.searchScopeGroupChatChip));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '群',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('更多群聊'), findsOneWidget);
    expect(find.text('更多联系人'), findsNothing);
  });

  testWidgets('输入关键词后展示实时联想并可展开联系人', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '李',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('最常使用'), findsOneWidget);
    expect(find.text('联系人'), findsWidgets);
    expect(find.text('更多联系人'), findsOneWidget);

    final moreContactsButton = find.ancestor(
      of: find.text('更多联系人'),
      matching: find.byType(CupertinoButton),
    );
    await tester.ensureVisible(moreContactsButton);
    await tester.pumpAndSettle();
    await tester.tap(moreContactsButton);
    await tester.pumpAndSettle();

    expect(find.text('李泽'), findsOneWidget);

    await tester.tap(find.text('李想').last);
    await tester.pumpAndSettle();

    expect(find.text('chat:conv_007'), findsOneWidget);
  });

  testWidgets('聊天记录可展开并直达对应对话页', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '群',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('更多聊天记录'), findsOneWidget);

    final moreChatRecordsButton = find.ancestor(
      of: find.text('更多聊天记录'),
      matching: find.byType(CupertinoButton),
    );
    await tester.ensureVisible(moreChatRecordsButton);
    await tester.pumpAndSettle();
    await tester.tap(moreChatRecordsButton);
    await tester.pumpAndSettle();

    expect(find.text('3人测试群'), findsWidgets);

    await tester.ensureVisible(find.text('3人测试群').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('3人测试群').first);
    await tester.pumpAndSettle();

    expect(find.text('chat:conv_grid_3'), findsOneWidget);
  });

  testWidgets('联系人没有单聊时回退到已存在群聊会话', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '王',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    await tester.tap(find.text('王芳').last);
    await tester.pumpAndSettle();

    expect(find.text('chat:conv_002'), findsOneWidget);
  });

  testWidgets('搜索网络结果入口打开独立网络结果页', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '冰',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    await tester.tap(find.text('冰').last);
    await tester.pumpAndSettle();

    expect(find.text('小趣搜'), findsWidgets);
    expect(find.text('推荐'), findsOneWidget);
  });

  testWidgets('主页网络建议可直达主页结果 tab', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '西湖',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('西湖 相关主页'), findsOneWidget);

    await tester.tap(find.text('西湖 相关主页'));
    await tester.pumpAndSettle();

    expect(find.text('主页'), findsOneWidget);
    expect(find.text('西湖景区'), findsWidgets);
  });
}

Map<String, dynamic> _historyEntry(String query) {
  return <String, dynamic>{
    'entryId': query,
    'query': query,
    'scope': SearchScope.all.wireValue,
    'updatedAt': DateTime(2026, 3, 22, 10).toIso8601String(),
  };
}
