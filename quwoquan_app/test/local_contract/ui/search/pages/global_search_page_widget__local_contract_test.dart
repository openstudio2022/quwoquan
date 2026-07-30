// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/full-screen-search-shell-and-entry/spec.md#gwt-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/full-screen-search-shell-and-entry/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/full-screen-search-shell-and-entry/spec.md#gwt-003
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/full-screen-search-shell-and-entry/spec.md#gwt-004
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import '../../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

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
      GoRoute(
        path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (context, state) {
          return Text('homepage:${state.pathParameters['id']}');
        },
      ),
      GoRoute(
        path: AppRoutePaths.userProfilePathTemplate.replaceAll(
          '{userHandle}',
          ':userHandle',
        ),
        builder: (context, state) {
          return Text('user:${state.pathParameters['userHandle']}');
        },
      ),
    ],
  );
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
  HomepageFacetSet? homepageRepository,
  RecentSearchQuery? recentSearchQuery,
  RecentSearchCommandWriter? recentSearchCommandWriter,
}) {
  final recentSearches = AlphaRecentSearchFacet();
  return ProviderScope(
    overrides: [
      searchRepositoryProvider.overrideWithValue(_FakeSearchRepository()),
      searchHotQueryReaderProvider.overrideWithValue(AlphaHotQueryReader()),
      recentSearchQueryProvider.overrideWithValue(
        recentSearchQuery ?? recentSearches,
      ),
      recentSearchCommandWriterProvider.overrideWithValue(
        recentSearchCommandWriter ?? recentSearches,
      ),
      searchFeedbackCommandWriterProvider.overrideWithValue(
        AlphaSearchFeedbackWriter(),
      ),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      assistantXiaoquSearchFacetProvider.overrideWithValue(
        _FakeAssistantRepository(),
      ),
      chatRepositoryCompositionProvider.overrideWithValue(MockChatRepository()),
      homepageFacetSetProvider.overrideWithValue(
        homepageRepository ?? MockHomepageRepository(),
      ),
    ],
    child: MaterialApp.router(
      routerConfig: _buildRouter(launchContext: launchContext),
    ),
  );
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  setUp(() async {
    // 最近搜索本地缓存清零；远端 RecentSearchState 由 typed port 承载，
    // widget 测试经 provider override 注入替身，无进程内共享状态需要复位。
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('默认页无结果 Tab 且展示搜索入口模块', (tester) async {
    tester.view.physicalSize = const Size(390, 1600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('小趣'), findsNothing);
    expect(find.text('全部'), findsNothing);
    expect(find.text('交集'), findsNothing);
    expect(find.text('图片'), findsNothing);
    expect(find.text('视频'), findsNothing);
    expect(find.text('长文'), findsNothing);
    expect(find.text('猜你想搜'), findsOneWidget);
    expect(find.text('发现圈子'), findsOneWidget);
    expect(find.text('发现地点'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('search_home_guess_refresh_button')),
      findsOneWidget,
    );
    expect(find.text('毕业旅行'), findsNothing);

    await tester.tap(
      find.byKey(const ValueKey<String>('search_home_guess_refresh_button')),
    );
    await tester.pumpAndSettle();

    expect(find.text('毕业旅行'), findsOneWidget);

    await tester.tap(find.text('发现圈子'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('search_home_guess_refresh_button')),
      findsNothing,
    );

    await tester.tap(find.text('发现地点'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('search_home_guess_refresh_button')),
      findsNothing,
    );
    expect(find.byKey(TestKeys.searchContentSelectorButton), findsNothing);
    expect(find.byKey(TestKeys.globalSearchScopeRail), findsNothing);
    expect(find.text('搜索历史'), findsNothing);
    expect(find.byKey(TestKeys.searchHistoryManageButton), findsNothing);
  });

  testWidgets('搜索历史手机默认两列五行并可展开收起', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await _seedHistory(<String>[
      '摄影圈',
      '旅行手账',
      '李明',
      '周末登山',
      '咖啡俱乐部',
      '夜景延时',
      '圈子搭子',
      '厦门大学',
      '鼓浪屿',
      '九寨沟',
      '环岛路',
      '旅行',
    ]);

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('搜索历史'), findsOneWidget);
    expect(find.text('展开'), findsOneWidget);
    expect(find.byKey(TestKeys.searchHistoryExpandButton), findsOneWidget);
    expect(find.text('环岛路'), findsNothing);

    await tester.tap(find.byKey(TestKeys.searchHistoryExpandButton));
    await tester.pumpAndSettle();

    expect(find.text('环岛路'), findsOneWidget);
    expect(find.text('收起'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.searchHistoryExpandButton));
    await tester.pumpAndSettle();

    expect(find.text('环岛路'), findsNothing);
  });

  testWidgets('搜索历史删除态支持单条删除与全部删除', (tester) async {
    await _seedHistory(<String>['摄影圈', '旅行手账']);

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.searchHistoryManageButton));
    await tester.pumpAndSettle();

    expect(find.text('全部删除'), findsOneWidget);
    expect(find.byKey(TestKeys.searchHistoryDoneButton), findsOneWidget);

    await tester.tap(find.byIcon(CupertinoIcons.xmark).first);
    await tester.pumpAndSettle();

    expect(find.text('摄影圈'), findsNothing);
    expect(find.text('旅行手账'), findsWidgets);

    await tester.tap(find.byKey(TestKeys.searchHistoryClearButton));
    await tester.pumpAndSettle();

    expect(find.text('清空搜索历史'), findsOneWidget);
    expect(find.text('将移除全部搜索历史记录，且无法恢复。'), findsOneWidget);

    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();

    expect(find.text('搜索历史'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.searchHistoryClearButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('清空').last);
    await tester.pumpAndSettle();

    expect(find.text('搜索历史'), findsNothing);
  });

  testWidgets('未完成远端 upsert 返回后不得复活已删除的本地搜索', (tester) async {
    const launchContext = SearchLaunchContext(entrySurfaceId: '/search');
    final recentSearches = _DelayedRecentSearchFacet();
    await tester.pumpWidget(
      _buildApp(
        launchContext: launchContext,
        recentSearchQuery: recentSearches,
        recentSearchCommandWriter: recentSearches,
      ),
    );
    await tester.pumpAndSettle();

    final pageContext = tester.element(find.byType(GlobalSearchPage));
    final container = ProviderScope.containerOf(pageContext);
    final provider = searchCoordinatorProvider(launchContext);
    final coordinator = container.read(provider.notifier);
    final upsert = coordinator.rememberCurrentQuery(query: '并发删除');
    await recentSearches.upsertStarted.future;
    await tester.pump();

    final localEntry = container.read(provider).recentSearches.single;
    await coordinator.removeRecentSearch(localEntry.entryId);
    recentSearches.completeUpsert(
      RecentSearchEntry(
        entryId: 'recent-canonical-delete-race',
        query: '并发删除',
        scope: SearchScope.all.wireValue,
        facet: null,
        updatedAt: DateTime.utc(2026, 7, 24, 12),
      ),
    );
    await upsert;
    await tester.pumpAndSettle();

    expect(container.read(provider).recentSearches, isEmpty);
    expect(
      recentSearches.deletedEntryIds,
      contains('recent-canonical-delete-race'),
    );
    final cached = await SearchRecentHistoryStore(
      actorNamespace: 'guest',
    ).load();
    expect(cached.entries, isEmpty);
    expect(cached.pendingUpsertKeys, isEmpty);
    expect(cached.pendingDeleteKeys, isEmpty);
  });

  testWidgets('重启后按语义删除回执清理 Remote canonical entryId', (tester) async {
    final recentSearches = AlphaRecentSearchFacet();
    final remoteEntry = await recentSearches.upsertRecentSearch(
      UpsertRecentSearchCommand(
        query: '待删除',
        scope: SearchScope.all.wireValue,
        facet: null,
      ),
    );
    await SearchRecentHistoryStore(actorNamespace: 'guest').save(
      const SearchRecentHistoryCacheSnapshot(
        pendingDeleteKeys: <String>{'all||待删除'},
      ),
    );

    await tester.pumpWidget(
      _buildApp(
        recentSearchQuery: recentSearches,
        recentSearchCommandWriter: recentSearches,
      ),
    );
    await tester.pumpAndSettle();

    expect(
      (await recentSearches.listRecentSearches(
        ListRecentSearchesQuery(),
      )).items,
      isEmpty,
      reason: '删除回执必须通过语义键解析服务端 canonical entryId',
    );
    expect(
      remoteEntry.entryId,
      isNot(
        RecentSearchEntryView.buildEntryId(
          query: '待删除',
          scope: SearchScope.all,
        ),
      ),
    );
    final cached = await SearchRecentHistoryStore(
      actorNamespace: 'guest',
    ).load();
    expect(cached.pendingDeleteKeys, isEmpty);
    expect(cached.entries, isEmpty);
  });

  testWidgets('输入关键词后展示本地匹配与搜索网络结果', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '李',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('搜索网络结果'), findsOneWidget);
    expect(find.text('联系人'), findsWidgets);

    final liXiangButton = find.ancestor(
      of: find.text('李想').last,
      matching: find.byType(CupertinoButton),
    );
    await tester.ensureVisible(liXiangButton.first);
    tester.widget<CupertinoButton>(liXiangButton.first).onPressed!.call();
    await tester.pumpAndSettle();

    expect(find.text('chat:conv_007'), findsOneWidget);
  });

  testWidgets('输入钱时输入框无 spinner 且东钱湖主页可直接打开', (tester) async {
    // homepageFacetSetProvider production 装配已收口 Remote-only；widget 测试
    // 必须显式注入 contract-seeded Mock（lite fixture 含东钱湖）。
    await tester.pumpWidget(
      _buildApp(homepageRepository: MockHomepageRepository()),
    );
    await tester.pumpAndSettle();

    final field = find.byKey(const ValueKey<String>('global_search_field'));
    await tester.enterText(field, '钱');
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(
      find.descendant(
        of: field,
        matching: find.byType(CupertinoActivityIndicator),
      ),
      findsNothing,
    );
    expect(find.text('东钱湖'), findsOneWidget);

    await tester.tap(find.text('东钱湖'));
    await tester.pumpAndSettle();
    expect(find.text('homepage:homepage_sight_dongqian_lake'), findsOneWidget);
  });

  testWidgets('查询替换后旧东钱湖 completion 不得回写', (tester) async {
    final homepages = _ManualHomepageRepository();
    await tester.pumpWidget(_buildApp(homepageRepository: homepages));
    await tester.pump();

    final field = find.byKey(const ValueKey<String>('global_search_field'));
    await tester.enterText(field, '钱');
    await tester.pump(const Duration(milliseconds: 220));
    await tester.enterText(field, '钱塘');
    await tester.pump(const Duration(milliseconds: 220));

    homepages.complete('钱', const <HomepageSummary>[
      HomepageSummary(
        id: 'homepage_sight_dongqian_lake',
        homepageType: 'sight',
        title: '东钱湖',
        status: 'published',
      ),
    ]);
    homepages.complete('钱塘', const <HomepageSummary>[]);
    await tester.pump();

    expect(find.text('东钱湖'), findsNothing);
  });

  testWidgets('云实体 3 秒提示一次且 5.9 秒返回仍可展示', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        homepageRepository: _DelayedHomepageRepository(
          Duration(milliseconds: 5900),
        ),
      ),
    );
    await tester.pump();

    final field = find.byKey(const ValueKey<String>('global_search_field'));
    await tester.enterText(field, '钱');
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pump(const Duration(milliseconds: 2959));

    expect(find.text(SearchText.searchWaitSlow), findsNothing);

    await tester.pump(const Duration(milliseconds: 1));
    expect(find.text(SearchText.searchWaitSlow), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 2899));
    expect(find.text('东钱湖'), findsNothing);

    await tester.pump(const Duration(milliseconds: 1));
    await tester.pump();
    expect(find.text('东钱湖'), findsOneWidget);
    expect(find.text(SearchText.searchWaitSlow), findsNothing);
  });

  testWidgets('云实体 6 秒未返回时停止 indicator 且不误报空态', (tester) async {
    await tester.pumpWidget(
      _buildApp(homepageRepository: _NeverCompletingHomepageRepository()),
    );
    await tester.pump();

    final field = find.byKey(const ValueKey<String>('global_search_field'));
    await tester.enterText(field, '钱');
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pump();
    // debounce 在 180ms 启动请求；当前时钟为 220ms，因此再推进 5959ms
    // 正好落在请求开始后的 5999ms。
    await tester.pump(const Duration(milliseconds: 5959));

    expect(
      find.byKey(const ValueKey<String>('global_search_network_progress')),
      findsOneWidget,
    );
    expect(find.text(SearchText.searchEmptyResult), findsNothing);

    await tester.pump(const Duration(milliseconds: 1));
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('global_search_network_progress')),
      findsNothing,
    );
    expect(find.text(SearchText.recoveryReloadLaterMessage), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(find.text(SearchText.searchEmptyResult), findsNothing);

    await tester.tap(find.text(SearchText.reload));
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('global_search_network_progress')),
      findsOneWidget,
    );
  });

  testWidgets('聊天记录最多三条且可直达对应对话页', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '群',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('3人测试群'), findsWidgets);
    expect(find.text('更多聊天记录'), findsNothing);

    await tester.ensureVisible(find.text('3人测试群').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('3人测试群').first);
    await tester.pumpAndSettle();

    expect(find.text('chat:conv_grid_3'), findsOneWidget);
  });

  testWidgets('聊天记录讨论缺失 avatarUrl 时显示稳定群占位', (tester) async {
    _suppressImageErrors();
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '群',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.byType(RoundedSquareAvatar).evaluate().isNotEmpty,
    );

    final avatar = tester.widget<RoundedSquareAvatar>(
      find.byType(RoundedSquareAvatar).first,
    );
    expect(avatar.imageUrl, isNull);
  });

  testWidgets('联系人没有单聊时进入联系人资料，不误开无关会话', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '王',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('王芳').evaluate().isNotEmpty,
    );

    await tester.tap(find.text('王芳').last);
    await _pumpUntil(
      tester,
      condition: () => find.text('user:wang_fang_public').evaluate().isNotEmpty,
    );

    expect(find.text('user:wang_fang_public'), findsOneWidget);
    expect(find.text('chat:conv_002'), findsNothing);
  });

  testWidgets('搜索网络结果入口打开独立网络结果页', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '冰',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('冰').evaluate().isNotEmpty,
    );

    await tester.tap(find.text('冰').last);
    await _pumpUntil(
      tester,
      condition: () => find.text('全部').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.text('推荐'), findsNothing);
  });

  testWidgets('主页网络建议可直达主页结果 tab', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '西湖',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖 交集').evaluate().isNotEmpty,
    );

    expect(find.text('西湖 交集'), findsOneWidget);

    await tester.tap(find.text('西湖 交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('交集').evaluate().isNotEmpty,
    );

    expect(find.text('交集'), findsWidgets);
  });
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  Duration step = const Duration(milliseconds: 50),
  int maxTicks = 80,
}) async {
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(step);
    if (condition()) {
      return;
    }
  }
  throw TestFailure('Timed out while waiting for condition.');
}

class _FakeSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode == SearchMode.suggest) {
      final hits = <SearchHit>[
        ..._contactHits(normalized.query),
        ..._conversationHits(normalized.query),
      ];
      return SearchResponse(request: normalized, sections: _sectionsFor(hits));
    }

    if (normalized.objectTypes.contains(SearchObjectType.entityHomepage) &&
        normalized.query == '西湖') {
      final hits = <SearchHit>[
        SearchHit(
          objectType: SearchObjectType.entityHomepage,
          objectId: 'homepage_west_lake',
          title: '西湖景区',
          subtitle: '杭州',
          resolvedFrom: SearchResolvedFrom.remote,
          payload: const SearchHitPayloadEntityHomepage(
            SearchEntityHomepageHitView(
              homepageId: 'homepage_west_lake',
              name: '西湖景区',
              subtitle: '杭州西湖风景名胜区',
              placeName: '杭州',
              address: '浙江省杭州市西湖区',
            ),
          ),
        ),
      ];
      return SearchResponse(request: normalized, sections: _sectionsFor(hits));
    }

    return SearchResponse(
      request: normalized,
      sections: const <SearchSection>[],
    );
  }

  List<SearchHit> _contactHits(String query) {
    switch (query) {
      case '李':
        return const <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_ming',
            title: '李明',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_li_ming',
                userHandle: 'li_ming_public',
                displayName: '李明',
                conversationId: 'conv_001',
              ),
            ),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_xiang',
            title: '李想',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_li_xiang',
                userHandle: 'li_xiang_public',
                displayName: '李想',
                conversationId: 'conv_007',
              ),
            ),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_qing',
            title: '李青',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_li_qing',
                userHandle: 'li_qing_public',
                displayName: '李青',
                conversationId: 'conv_008',
              ),
            ),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_yue',
            title: '李悦',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_li_yue',
                userHandle: 'li_yue_public',
                displayName: '李悦',
                conversationId: 'conv_009',
              ),
            ),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_ze',
            title: '李泽',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_li_ze',
                userHandle: 'li_ze_public',
                displayName: '李泽',
                conversationId: 'conv_010',
              ),
            ),
          ),
        ];
      case '王':
        return const <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_wang_fang',
            title: '王芳',
            resolvedFrom: SearchResolvedFrom.local,
            payload: SearchHitPayloadChatContact(
              ChatContactSearchItemDto(
                contactId: 'user_wang_fang',
                userHandle: 'wang_fang_public',
                displayName: '王芳',
              ),
            ),
          ),
        ];
      default:
        return const <SearchHit>[];
    }
  }

  List<SearchHit> _conversationHits(String query) {
    if (query != '群') {
      return const <SearchHit>[];
    }
    return const <SearchHit>[
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_002',
        title: '周末登山群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: SearchHitPayloadChatConversation(
          ConversationSearchItemView(
            conversationId: 'conv_002',
            type: 'group',
            title: '周末登山群',
            memberCount: 15,
            lastMessagePreview: '周六早上8点出发',
          ),
        ),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_3',
        title: '3人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: SearchHitPayloadChatConversation(
          ConversationSearchItemView(
            conversationId: 'conv_grid_3',
            type: 'group',
            title: '3人测试群',
            memberCount: 3,
            lastMessagePreview: '测试群聊',
          ),
        ),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_4',
        title: '4人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: SearchHitPayloadChatConversation(
          ConversationSearchItemView(
            conversationId: 'conv_grid_4',
            type: 'group',
            title: '4人测试群',
            memberCount: 4,
            lastMessagePreview: '测试群聊',
          ),
        ),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_5',
        title: '5人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: SearchHitPayloadChatConversation(
          ConversationSearchItemView(
            conversationId: 'conv_grid_5',
            type: 'group',
            title: '5人测试群',
            memberCount: 5,
            lastMessagePreview: '测试群聊',
          ),
        ),
      ),
    ];
  }

  List<SearchSection> _sectionsFor(List<SearchHit> hits) {
    final contacts = hits
        .where((item) => item.objectType == SearchObjectType.chatContact)
        .toList(growable: false);
    final conversations = hits
        .where((item) => item.objectType == SearchObjectType.chatConversation)
        .toList(growable: false);
    final homepages = hits
        .where((item) => item.objectType == SearchObjectType.entityHomepage)
        .toList(growable: false);
    return <SearchSection>[
      if (contacts.isNotEmpty)
        SearchSection(
          id: 'contacts',
          title: '联系人',
          objectTypes: const <SearchObjectType>[SearchObjectType.chatContact],
          hits: contacts,
          resolvedFrom: SearchResolvedFrom.local,
        ),
      if (conversations.isNotEmpty)
        SearchSection(
          id: 'chat_records',
          title: '聊天记录',
          objectTypes: const <SearchObjectType>[
            SearchObjectType.chatConversation,
          ],
          hits: conversations,
          resolvedFrom: SearchResolvedFrom.local,
        ),
      if (homepages.isNotEmpty)
        SearchSection(
          id: 'homepages',
          title: '主页',
          objectTypes: const <SearchObjectType>[
            SearchObjectType.entityHomepage,
          ],
          hits: homepages,
          resolvedFrom: SearchResolvedFrom.remote,
        ),
    ];
  }
}

class _ManualHomepageRepository extends MockHomepageRepository {
  final Map<String, Completer<List<HomepageSummary>>> _pending =
      <String, Completer<List<HomepageSummary>>>{};

  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = 20,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    final normalized = query.trim();
    if (normalized.isEmpty) {
      return Future<List<HomepageSummary>>.value(const []);
    }
    return _pending
        .putIfAbsent(normalized, () => Completer<List<HomepageSummary>>())
        .future;
  }

  void complete(String query, List<HomepageSummary> values) {
    _pending
        .putIfAbsent(query, () => Completer<List<HomepageSummary>>())
        .complete(values);
  }
}

class _NeverCompletingHomepageRepository extends MockHomepageRepository {
  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = 20,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    if (query.trim().isEmpty) {
      return Future<List<HomepageSummary>>.value(const []);
    }
    final signal = cancellation;
    if (signal == null) return Completer<List<HomepageSummary>>().future;
    return signal.whenCancelled.then<List<HomepageSummary>>((_) {
      throw const CloudOperationCancelledException();
    });
  }
}

class _DelayedHomepageRepository extends MockHomepageRepository {
  _DelayedHomepageRepository(this.delay);

  final Duration delay;

  @override
  Future<List<HomepageSummary>> searchHomepages({
    required String query,
    String? homepageType,
    String? city,
    String? status,
    int limit = 20,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    if (query.trim().isEmpty) {
      return Future<List<HomepageSummary>>.value(const []);
    }
    final completion = Future<List<HomepageSummary>>.delayed(
      delay,
      () => const <HomepageSummary>[
        HomepageSummary(
          id: 'homepage_sight_dongqian_lake',
          homepageType: 'sight',
          title: '东钱湖',
          status: 'published',
        ),
      ],
    );
    if (cancellation == null) return completion;
    return Future.any<List<HomepageSummary>>(<Future<List<HomepageSummary>>>[
      completion,
      cancellation.whenCancelled.then<List<HomepageSummary>>((_) {
        throw const CloudOperationCancelledException();
      }),
    ]);
  }
}

class _FakeAssistantRepository implements AssistantXiaoquSearchFacet {
  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    return AssistantSearchResultView(
      queryEcho: query,
      summary: '$query 的推荐结果',
      searchIntensity: searchIntensity,
      citations: <AssistantSearchCitationView>[
        AssistantSearchCitationView(
          citationId: 'citation_1',
          objectType: 'content.post',
          objectId: 'post_1',
          title: '冰雪旅行推荐',
          snippet: '适合冬季出行的内容推荐',
          sourceDomain: '小趣搜',
          destination: CitationDestination(
            kind: CitationDestinationKind.internal,
            objectTypeRef: 'content.post',
            objectId: 'post_1',
          ),
        ),
      ],
    );
  }
}

final class _DelayedRecentSearchFacet
    implements RecentSearchQuery, RecentSearchCommandWriter {
  final Completer<void> upsertStarted = Completer<void>();
  final Completer<RecentSearchEntry> _upsertResult =
      Completer<RecentSearchEntry>();
  final List<String> deletedEntryIds = <String>[];
  RecentSearchEntry? _entry;

  void completeUpsert(RecentSearchEntry entry) {
    _upsertResult.complete(entry);
  }

  @override
  Future<RecentSearchEntrySlice> listRecentSearches(
    ListRecentSearchesQuery query,
  ) async {
    final entry = _entry;
    return RecentSearchEntrySlice(
      items: entry == null
          ? const <RecentSearchEntry>[]
          : <RecentSearchEntry>[entry],
    );
  }

  @override
  Future<RecentSearchEntry> upsertRecentSearch(
    UpsertRecentSearchCommand command,
  ) async {
    if (!upsertStarted.isCompleted) {
      upsertStarted.complete();
    }
    final entry = await _upsertResult.future;
    _entry = entry;
    return entry;
  }

  @override
  Future<void> deleteRecentSearch(DeleteRecentSearchCommand command) async {
    deletedEntryIds.add(command.entryId);
    if (_entry?.entryId == command.entryId) {
      _entry = null;
    }
  }

  @override
  Future<void> clearRecentSearches(ClearRecentSearchesCommand command) async {
    _entry = null;
  }
}

Future<void> _seedHistory(List<String> queries) {
  final updatedAt = DateTime(2026, 3, 22, 10);
  final entries = queries
      .map(
        (query) => RecentSearchEntryView(
          entryId: 'local-pending-$query',
          query: query,
          scope: SearchScope.all,
          facet: null,
          updatedAt: updatedAt,
        ),
      )
      .toList(growable: false);
  return SearchRecentHistoryStore(actorNamespace: 'guest').save(
    SearchRecentHistoryCacheSnapshot(
      entries: entries,
      pendingUpsertKeys: queries
          .map((query) => 'all||${query.toLowerCase()}')
          .toSet(),
    ),
  );
}
