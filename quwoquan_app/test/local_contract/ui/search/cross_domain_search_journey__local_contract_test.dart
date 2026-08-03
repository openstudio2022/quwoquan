// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import '../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';

/// 跨域搜索 T4 旅程（SIT1）：
/// suggest 本地两阶段、result 云侧固定 Tab、本地对象不进 result、最近搜索、
/// 单域降级不阻塞整页、整页错误态可重试、referralSource/feedRequestId 埋点归因链。
///
/// 与 page widget 测试互补：本文件验证「跨页旅程 + 归因链 + 降级/错误态闭环」，
/// 不重复各页内部细分渲染断言。
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
          final effective = state.extra is SearchLaunchContext
              ? state.extra! as SearchLaunchContext
              : launchContext;
          return GlobalSearchPage(launchContext: effective);
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
        builder: (context, state) => Text('chat:${state.pathParameters['id']}'),
      ),
    ],
  );
}

Widget _buildApp({
  required SearchRepository searchRepository,
  AssistantSearchRunFacet? assistantXiaoquSearch,
  BehaviorRepository? behaviorRepository,
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
}) {
  final recentSearches = AlphaRecentSearchFacet();
  return ProviderScope(
    overrides: [
      searchRepositoryProvider.overrideWithValue(searchRepository),
      searchHotQueryReaderProvider.overrideWithValue(AlphaHotQueryReader()),
      recentSearchQueryProvider.overrideWithValue(recentSearches),
      recentSearchCommandWriterProvider.overrideWithValue(recentSearches),
      searchFeedbackCommandWriterProvider.overrideWithValue(
        AlphaSearchFeedbackWriter(),
      ),
      assistantSearchRunFacetProvider.overrideWithValue(
        assistantXiaoquSearch ?? _FakeAssistantRepository(),
      ),
      chatRepositoryCompositionProvider.overrideWithValue(MockChatRepository()),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
      homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
      if (behaviorRepository != null)
        behaviorRepositoryProvider.overrideWithValue(behaviorRepository),
    ],
    child: MaterialApp.router(
      routerConfig: _buildRouter(launchContext: launchContext),
    ),
  );
}

/// 直接以深链方式打开 result 页（绕过 suggest），用于降级/错误态闭环验证。
Widget _buildResultsPage({
  required SearchRepository searchRepository,
  AssistantSearchRunFacet? assistantXiaoquSearch,
  required SearchLaunchContext launchContext,
}) {
  return ProviderScope(
    overrides: [
      searchRepositoryProvider.overrideWithValue(searchRepository),
      searchFeedbackCommandWriterProvider.overrideWithValue(
        AlphaSearchFeedbackWriter(),
      ),
      assistantSearchRunFacetProvider.overrideWithValue(
        assistantXiaoquSearch ?? _FakeAssistantRepository(),
      ),
      chatRepositoryCompositionProvider.overrideWithValue(MockChatRepository()),
      circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
    ],
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

ContentBehaviorTracker _trackerOf(WidgetTester tester, Type pageType) {
  final element = tester.element(find.byType(pageType));
  return ProviderScope.containerOf(
    element,
  ).read(contentBehaviorTrackerProvider);
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    // 最近搜索本地缓存清零；远端 RecentSearchState 经 search 域 typed port
    // 承载，测试内无进程级共享 mock 状态需要复位。
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  Future<void> sizeAndPump(WidgetTester tester, Widget widget) async {
    tester.view.physicalSize = const Size(1080, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(widget);
  }

  testWidgets('两阶段旅程：suggest 本地命中后进入云侧固定 Tab，本地对象不进 result', (tester) async {
    await sizeAndPump(
      tester,
      _buildApp(searchRepository: _JourneySearchRepository()),
    );
    await tester.pumpAndSettle();

    // 阶段一：suggest 本地快速检索（联系人本地命名空间）。
    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '西湖',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖向导').evaluate().isNotEmpty,
    );
    expect(find.text('联系人'), findsWidgets);
    // 此时仍在 suggest 默认页，未出现 result 固定 Tab。
    expect(find.byType(SearchNetworkResultsPage), findsNothing);

    // 阶段二：点击网络结果入口进入云侧结果页。
    await tester.tap(find.text('西湖').last);
    await _pumpUntil(
      tester,
      condition: () =>
          find.byType(SecondaryCapsuleTabBar).evaluate().isNotEmpty,
    );
    await _pumpUntil(
      tester,
      condition: () => find.text('实体主页').evaluate().isNotEmpty,
    );

    // result 固定 Tab 只来自云侧契约顺序。
    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs, <String>['小趣', '全部', '交集', '图片', '视频', '长文']);

    // 云侧 entity.homepage 顶卡 + 云侧 content.post 命中。
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖夜景延时'), findsWidgets);

    // 本地 suggest 对象（联系人）不得进入 result 页子树。
    final resultsSubtree = find.byType(SearchNetworkResultsPage);
    expect(
      find.descendant(of: resultsSubtree, matching: find.text('西湖向导')),
      findsNothing,
    );
    expect(
      find.descendant(of: resultsSubtree, matching: find.text('联系人')),
      findsNothing,
    );
  });

  testWidgets('suggest 本地命中可点击落地到对应会话页', (tester) async {
    await sizeAndPump(
      tester,
      _buildApp(searchRepository: _JourneySearchRepository()),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '西湖',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖向导').evaluate().isNotEmpty,
    );

    await tester.ensureVisible(find.text('西湖向导').last);
    await tester.tap(find.text('西湖向导').last);
    await _pumpUntil(
      tester,
      condition: () => find.text('chat:conv_west_lake').evaluate().isNotEmpty,
    );
    expect(find.text('chat:conv_west_lake'), findsOneWidget);
  });

  testWidgets('最近搜索本地水合后可见并可重新发起 suggest', (tester) async {
    final cachedEntry = RecentSearchEntryView(
      entryId: 'local-pending-west-lake',
      query: '西湖',
      scope: SearchScope.all,
      facet: null,
      updatedAt: DateTime(2026, 3, 22, 10),
    );
    await SearchRecentHistoryStore(actorNamespace: 'guest').save(
      SearchRecentHistoryCacheSnapshot(
        entries: <RecentSearchEntryView>[cachedEntry],
        pendingUpsertKeys: const <String>{'all||西湖'},
      ),
    );
    await sizeAndPump(
      tester,
      _buildApp(searchRepository: _JourneySearchRepository()),
    );
    await tester.pumpAndSettle();

    expect(find.text('搜索历史'), findsOneWidget);
    expect(find.text('西湖'), findsWidgets);
    final hydratedCache = await SearchRecentHistoryStore(
      actorNamespace: 'guest',
    ).load();
    expect(hydratedCache.pendingUpsertKeys, isEmpty);
    expect(
      hydratedCache.entries.single.entryId,
      isNot('local-pending-west-lake'),
      reason: 'Remote 回填成功后必须持久化 canonical entryId',
    );

    await tester.tap(find.text('西湖').first);
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖向导').evaluate().isNotEmpty,
    );
    expect(find.text('西湖向导'), findsWidgets);
  });

  testWidgets('单域失败只显该域降级且不阻塞整页其它结果', (tester) async {
    await sizeAndPump(
      tester,
      _buildResultsPage(
        searchRepository: _ContentDomainFailingRepository(),
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'all',
        ),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('实体主页').evaluate().isNotEmpty,
    );

    // content 域抛错被守卫降级，entity 域仍展示，整页未进入页级错误态。
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('整页加载失败展示错误态并可重试恢复', (tester) async {
    final assistant = _FlakyXiaoquAssistantRepository();
    // 以小趣 Tab 深链直接打开 result 页（小趣检索不经守卫，整页失败可被观测）。
    await sizeAndPump(
      tester,
      _buildResultsPage(
        searchRepository: _JourneySearchRepository(),
        assistantXiaoquSearch: assistant,
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'xiaoqu',
        ),
      ),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(AppPageErrorState).evaluate().isNotEmpty,
    );
    expect(find.byType(AppPageErrorState), findsOneWidget);

    // 第二次调用成功，触发错误态主操作回调（retry）→ 重新加载恢复。
    assistant.failNext = false;
    final errorState = tester.widget<AppPageErrorState>(
      find.byType(AppPageErrorState),
    );
    expect(errorState.onAction, isNotNull);
    await errorState.onAction!(
      const UiErrorAction(type: UiErrorActionType.retry, label: '重试'),
    );
    await _pumpUntil(
      tester,
      condition: () => find.byType(AppPageErrorState).evaluate().isEmpty,
      maxTicks: 120,
    );
    expect(find.byType(AppPageErrorState), findsNothing);
  });

  testWidgets('默认页与结果页埋点归因链：referralSource=search + feedRequestId', (
    tester,
  ) async {
    final behavior = MockBehaviorRepository();
    await sizeAndPump(
      tester,
      _buildApp(
        searchRepository: _JourneySearchRepository(),
        behaviorRepository: behavior,
      ),
    );
    await tester.pumpAndSettle();

    // 默认页曝光归因。
    final homeTracker = _trackerOf(tester, GlobalSearchPage);
    await homeTracker.flush();
    final homeImpression = behavior.recorded.firstWhere(
      (e) =>
          e.action == BehaviorAction.impression &&
          e.contentId == 'global_search',
      orElse: () => throw TestFailure('missing global_search impression'),
    );
    expect(homeImpression.referralSource, ReferralSource.search);
    expect(homeImpression.feedRequestId, isNotNull);
    expect(homeImpression.feedRequestId, isNotEmpty);

    // 进入结果页。
    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '西湖',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖').evaluate().isNotEmpty,
    );
    await tester.tap(find.text('西湖').last);
    await _pumpUntil(
      tester,
      condition: () =>
          find.byType(SearchNetworkResultsPage).evaluate().isNotEmpty,
    );
    await tester.pump();

    final resultTracker = _trackerOf(tester, SearchNetworkResultsPage);
    await resultTracker.flush();
    final resultImpression = behavior.recorded.firstWhere(
      (e) =>
          e.action == BehaviorAction.impression &&
          e.contentId == 'search_network_results',
      orElse: () =>
          throw TestFailure('missing search_network_results impression'),
    );
    expect(resultImpression.referralSource, ReferralSource.search);
    expect(resultImpression.feedRequestId, isNotNull);
    expect(resultImpression.feedRequestId, isNotEmpty);
    expect(resultImpression.channelId, 'all');
    expect(
      resultImpression.tags,
      anyOf(isNull, isEmpty),
      reason: '原始查询词与 surface/tab 不能伪装成 canonical tagRefs',
    );
  });
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
  Duration step = const Duration(milliseconds: 50),
  int maxTicks = 100,
}) async {
  for (var i = 0; i < maxTicks; i++) {
    await tester.pump(step);
    if (condition()) {
      return;
    }
  }
  throw TestFailure('Timed out while waiting for condition.');
}

/// 旅程主仓库：suggest 返回本地联系人/会话；result 返回云侧 entity/location/post。
class _JourneySearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode == SearchMode.suggest) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[
          SearchSection(
            id: 'contacts',
            title: '联系人',
            objectTypes: <SearchObjectType>[SearchObjectType.chatContact],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.chatContact,
                objectId: 'contact_west_lake',
                title: '西湖向导',
                resolvedFrom: SearchResolvedFrom.local,
                payload: SearchHitPayloadChatContact(
                  ChatContactSearchItemDto(
                    contactId: 'contact_west_lake',
                    displayName: '西湖向导',
                    conversationId: 'conv_west_lake',
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.local,
          ),
        ],
      );
    }
    return _cloudResult(normalized);
  }
}

SearchResponse _cloudResult(
  SearchRequest normalized, {
  bool contentDomainFails = false,
}) {
  final sections = <SearchSection>[];
  final degradeSignals = <SearchDegradeSignal>[];
  if (normalized.objectTypes.contains(SearchObjectType.entityHomepage)) {
    sections.add(
      const SearchSection(
        id: 'homepages',
        title: '主页',
        objectTypes: <SearchObjectType>[SearchObjectType.entityHomepage],
        hits: <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.entityHomepage,
            objectId: 'homepage_west_lake',
            title: '西湖',
            subtitle: '杭州',
            snippet: '杭州热门地点',
            resolvedFrom: SearchResolvedFrom.remote,
            payload: SearchHitPayloadWireMap(<String, dynamic>{
              'id': 'homepage_west_lake',
              'title': '西湖',
              'followerCount': 1200,
              'contentCount': 340,
            }),
          ),
        ],
        resolvedFrom: SearchResolvedFrom.remote,
      ),
    );
  }
  if (normalized.objectTypes.contains(SearchObjectType.locationPlace)) {
    sections.add(
      const SearchSection(
        id: 'locations',
        title: '位置',
        objectTypes: <SearchObjectType>[SearchObjectType.locationPlace],
        hits: <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.locationPlace,
            objectId: 'place_west_lake_alley',
            title: '西湖旁断桥小巷',
            subtitle: '杭州',
            resolvedFrom: SearchResolvedFrom.remote,
            payload: SearchHitPayloadWireMap(<String, dynamic>{
              'objectId': 'place_west_lake_alley',
              'connectionState': 'connected',
            }),
          ),
        ],
        resolvedFrom: SearchResolvedFrom.remote,
      ),
    );
  }
  if (normalized.objectTypes.contains(SearchObjectType.contentPost) &&
      contentDomainFails) {
    degradeSignals.add(
      const SearchDegradeSignal(
        code: 'content_remote_failed',
        message: '内容单域暂不可用',
        objectType: SearchObjectType.contentPost,
      ),
    );
  } else if (normalized.objectTypes.contains(SearchObjectType.contentPost)) {
    const item = PostSearchItemView(
      postId: 'post_west_lake_timelapse',
      contentType: 'video',
      contentIdentity: 'work',
      title: '西湖夜景延时',
      summary: '云侧内容命中',
      coverUrl:
          'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
      authorDisplayName: '延时摄影师',
      likeCount: 88,
    );
    sections.add(
      SearchSection(
        id: 'content',
        title: '内容',
        objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
        hits: <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.contentPost,
            objectId: item.postId,
            title: item.title ?? item.postId,
            snippet: item.summary,
            resolvedFrom: SearchResolvedFrom.remote,
            payload: SearchHitPayloadContentPost(item),
          ),
        ],
        resolvedFrom: SearchResolvedFrom.remote,
      ),
    );
  }
  return SearchResponse(
    request: normalized,
    sections: sections,
    degradeSignals: degradeSignals,
  );
}

/// content 域抛错，entity/location 正常：验证单域失败不阻塞整页。
class _ContentDomainFailingRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode == SearchMode.suggest) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    return _cloudResult(normalized, contentDomainFails: true);
  }
}

class _FlakyXiaoquAssistantRepository extends _FakeAssistantRepository {
  bool failNext = true;

  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    if (failNext) {
      throw StateError('xiaoqu backend unavailable');
    }
    return super.executeAssistantSearch(
      query: query,
      sessionClientRequestId: sessionClientRequestId,
      runClientRequestId: runClientRequestId,
      searchIntensity: searchIntensity,
      contextSnapshot: contextSnapshot,
    );
  }
}

class _FakeAssistantRepository implements AssistantSearchRunFacet {
  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    return AssistantRunTerminalSnapshotView(
      answerText: '$query 的推荐结果',
      processes: <AssistantRunVisibleProcessView>[
        AssistantRunVisibleProcessView(
          processId: 'search-process-1',
          scope: 'public_web',
          stage: 'retrieval',
          actionCode: 'search',
          status: 'completed',
          order: 1,
          summary: '已整理公开线索',
          skillId: 'web_search',
          domainId: 'search',
          searchedDocumentCount: 1,
          processedDocumentCount: 1,
          acceptedDocumentCount: 1,
          acceptedReferences: <AssistantRunVisibleReferenceView>[
            AssistantRunVisibleReferenceView(
              title: '西湖夜景推荐',
              snippet: '小趣整理的推荐结果',
              source: '小趣搜',
              destination: CitationDestination(
                kind: CitationDestinationKind.internal,
                objectTypeRef: 'content.post',
                objectId: 'post_1',
              ),
            ),
          ],
        ),
      ],
    );
  }
}
