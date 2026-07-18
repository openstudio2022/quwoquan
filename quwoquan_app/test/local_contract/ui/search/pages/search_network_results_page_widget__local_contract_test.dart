import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
    prefilledQuery: '影',
    initialNetworkTabId: 'all',
  ),
}) {
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
    ],
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

Widget _buildAppWithSearchRepository({
  required SearchLaunchContext launchContext,
  required SearchRepository repository,
}) {
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(MockCircleRepository()),
      searchRepositoryProvider.overrideWithValue(repository),
    ],
    child: MaterialApp(
      home: SearchNetworkResultsPage(launchContext: launchContext),
    ),
  );
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  Future<void> pumpSearchResultsPage(WidgetTester tester, Widget widget) async {
    tester.view.physicalSize = const Size(1080, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(widget);
  }

  testWidgets('网络结果页固定 Tab 并默认进入全部', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(find.text('小趣'), findsOneWidget);
    expect(find.text('全部'), findsWidgets);
    expect(
      tester.getTopLeft(find.text('小趣')).dx,
      lessThan(tester.getTopLeft(find.text('全部').first).dx),
    );
    expect(find.text('交集'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('长文'), findsOneWidget);
    expect(find.textContaining('已加入圈子'), findsNothing);
    expect(find.textContaining('聊天记录'), findsNothing);
    expect(find.textContaining('全站结果'), findsNothing);
    expect(find.text('相关搜索'), findsWidgets);
    expect(find.text('影 攻略'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
    expect(find.text('推荐'), findsNothing);
    expect(find.text('遇见'), findsNothing);
    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs, <String>['小趣', '全部', '交集', '图片', '视频', '长文']);
    expect(find.textContaining('小趣正在整理'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('search_network_submit_button')),
      findsOneWidget,
    );
  });

  testWidgets('正式结果页每个 generation 只调用一次 canonical search', (tester) async {
    final repository = _RecordingCanonicalSearchRepository();
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: repository,
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(repository.requests, hasLength(1));
    expect(repository.requests.single.objectTypes, <SearchObjectType>{
      SearchObjectType.contentPost,
      SearchObjectType.entityHomepage,
      SearchObjectType.locationPlace,
    });
  });

  testWidgets('结果页搜索按钮可按新关键词重新加载', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    await tester.enterText(
      find.byKey(const ValueKey<String>('search_network_field')),
      '西湖',
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('search_network_submit_button')),
    );
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖').evaluate().isNotEmpty,
    );

    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖摄影讨论'), findsNothing);
  });

  testWidgets('交集 tab 按云侧 connectionState 分组并只读 primaryText', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '影',
          initialNetworkTabId: 'all',
        ),
        repository: _IntersectionContractSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.text('交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('已形成的连接').evaluate().isNotEmpty,
    );

    // connectionState=connected 的命中进入「已形成的连接」。
    expect(find.text('已形成的连接'), findsOneWidget);
    expect(find.text('你点赞过的海边日落'), findsWidgets);

    // intersection_lead / unconnected 的命中进入「发现更多交集」。
    expect(find.text('发现更多交集'), findsOneWidget);
    expect(find.text('环岛路骑行机位合集'), findsWidgets);
    expect(find.text('城市天际线拍摄攻略'), findsWidgets);

    // 交集句严格只读云侧 intersectionReason.primaryText。
    expect(find.text('你关注的小林也在拍这里'), findsWidgets);

    // 无 primaryText 的命中不得出现端侧拼装/旧字段回退/违禁词。
    expect(find.textContaining('共同兴趣'), findsNothing);
    expect(find.textContaining('感兴趣圈子'), findsNothing);
    expect(find.textContaining('交集发现流'), findsNothing);
    expect(find.textContaining('好友'), findsNothing);
    expect(find.textContaining('因为你'), findsNothing);
  });

  testWidgets('全部 tab 顶卡只来自云侧 entity.homepage 单源', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('实体主页').evaluate().isNotEmpty,
    );

    // 顶卡走 entity.homepage（badge=实体主页 + 关注/内容计数来自 payload）。
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖'), findsWidgets);
    // 不再出现三方 POI 旁路（integration.location_poi 已下线于结果页）。
    expect(find.text('浙江省杭州市西湖区'), findsNothing);
  });

  testWidgets('交集 tab 已连接地点来自云侧 location.place', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.text('交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('已形成的连接').evaluate().isNotEmpty,
    );

    // connectionState=connected 的 location.place 进入「已形成的连接」。
    expect(find.text('已形成的连接'), findsOneWidget);
    expect(find.textContaining('西湖旁断桥小巷'), findsWidgets);
  });

  testWidgets('旧主页 tab 深链归一到全部', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildApp(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'homepages',
        ),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs[tabBar.activeIndex], '全部');
  });

  testWidgets('全部 tab 只汇总实体顶部、媒体文章和相关搜索', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('相关搜索').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.textContaining('聊天记录'), findsNothing);
    expect(find.text('光影摄影社主群'), findsNothing);
    expect(find.text('相关搜索'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
    expect(find.textContaining('全站结果'), findsNothing);
  });

  testWidgets('旧消息 tab 深链归一到全部但不展示聊天结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'messages',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.text('实体主页'), findsOneWidget);
    expect(find.text('西湖摄影讨论'), findsNothing);
  });

  testWidgets('小趣 tab 可作为初始 tab 打开', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '露营',
          initialNetworkTabId: 'xiaoqu',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('小趣'), findsWidgets);
    expect(find.textContaining('正在为你整理'), findsWidgets);
  });

  testWidgets('不存在的 locations tab 归一到综合避免空 tab 漂移', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '西湖',
          initialNetworkTabId: 'locations',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(tabBar.tabs[tabBar.activeIndex], '全部');
  });

  testWidgets('degrade signal 不压过媒体结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'all',
        ),
        repository: _DegradedNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.searchPartialGroupFailed), findsOneWidget);
    expect(find.text('街头摄影'), findsWidgets);
  });

  testWidgets('degrade signal 在无结果时展示降级横幅', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '空结果词',
          initialNetworkTabId: 'all',
        ),
        repository: _EmptyDegradedNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.searchPartialGroupFailed), findsOneWidget);
  });

  testWidgets('内容类型筛选可驱动网络结果页加载指定内容结果', (tester) async {
    await pumpSearchResultsPage(
      tester,
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: 'UI',
          initialNetworkTabId: 'humanity',
          searchObjectSelection: SearchObjectSelection(
            contentTypes: <SearchContentTypeFilter>{
              SearchContentTypeFilter.article,
            },
          ),
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('全部'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
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

class _FakeNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.objectTypes.length > 1) {
      final responses = await Future.wait<SearchResponse>(
        normalized.objectTypes.map(
          (objectType) => search(
            SearchRequest(
              query: normalized.query,
              mode: normalized.mode,
              objectTypes: <SearchObjectType>{objectType},
              limit: normalized.limit,
              contentTypes: normalized.contentTypes,
              categoryId: normalized.categoryId,
              subCategory: normalized.subCategory,
            ),
            cancellation: cancellation,
            deadlineAt: deadlineAt,
          ),
        ),
      );
      final sections = <SearchSection>[];
      final sectionIds = <String>{};
      for (final response in responses) {
        for (final section in response.sections) {
          if (sectionIds.add(section.id)) sections.add(section);
        }
      }
      return SearchResponse(request: normalized, sections: sections);
    }
    if (normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      final wantsArticle = normalized.contentTypes.contains(
        SearchContentTypeFilter.article,
      );
      final item = PostSearchItemView.fromMap(<String, dynamic>{
        'postId': 'fake_street_photo',
        'contentType': wantsArticle ? 'article' : 'image',
        'contentIdentity': wantsArticle ? 'article' : 'work',
        'title': '街头摄影',
        'summary': '摄影频道结果',
        'coverUrl':
            'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
        'authorDisplayName': '街头摄影',
        'categoryId': normalized.categoryId ?? 'photography',
        'subCategory': '影像',
        'likeCount': 32,
        'matchedField': 'author',
      });
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'content',
            title: '内容',
            objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.contentPost,
                objectId: item.postId,
                title: item.title ?? item.postId,
                subtitle: item.authorDisplayName,
                snippet: item.summary,
                resolvedFrom: SearchResolvedFrom.remote,
                matchedField: item.matchedField,
                payload: SearchHitPayloadContentPost(item),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.circleGroup) ||
        normalized.objectTypes.contains(SearchObjectType.circleCircle)) {
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'groups',
            title: '讨论',
            objectTypes: const <SearchObjectType>[
              SearchObjectType.circleGroup,
              SearchObjectType.circleCircle,
            ],
            hits: const <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.circleGroup,
                objectId: 'group_light_photo',
                title: '光影摄影社主群',
                subtitle: '圈子主群',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadWireMap(<String, dynamic>{
                  'circleId': 'fixture_circle_photo',
                  'groupId': 'group_light_photo',
                  'name': '光影摄影社主群',
                  'description': '圈子主群',
                  'circleName': '光影摄影社',
                }),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.chatConversation) ||
        normalized.objectTypes.contains(SearchObjectType.chatMessage)) {
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'chat_records',
            title: '聊天记录',
            objectTypes: const <SearchObjectType>[
              SearchObjectType.chatConversation,
              SearchObjectType.chatMessage,
            ],
            hits: const <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.chatMessage,
                objectId: 'msg_west_lake',
                title: '西湖摄影讨论',
                subtitle: '光影摄影社主群',
                snippet: '周末西湖拍摄路线和集合时间',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadWireMap(<String, dynamic>{
                  'conversationId': 'group_light_photo',
                  'messageId': 'msg_west_lake',
                }),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    if (normalized.objectTypes.contains(SearchObjectType.entityHomepage) ||
        normalized.objectTypes.contains(SearchObjectType.locationPlace)) {
      // 顶卡云侧单源：entity.homepage（已绑定实体主页）。一方地点 location.place
      // 仅在 connectionState=connected 时进交集「已形成的连接」。
      final sections = <SearchSection>[];
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
                snippet: '被内容引用但未绑定主页的自由文本地点',
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
      return SearchResponse(request: normalized, sections: sections);
    }
    if (normalized.objectTypes.contains(SearchObjectType.userProfile)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[
          SearchSection(
            id: 'users',
            title: '人',
            objectTypes: <SearchObjectType>[SearchObjectType.userProfile],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.userProfile,
                objectId: 'user_photo_friend',
                title: '林同学',
                subtitle: '摄影爱好者',
                snippet: '摄影同好',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadWireMap(<String, dynamic>{
                  'subAccountId': 'user_photo_friend',
                  'username': 'user_photo_friend',
                  'displayName': '林同学',
                  'headline': '摄影爱好者',
                  'chatAvailable': true,
                  'relationshipCapability': <String, dynamic>{
                    'relationState': 'mutual',
                    'canFollow': false,
                    'canUnfollow': true,
                    'canOpenConversation': true,
                  },
                }),
              ),
              SearchHit(
                objectType: SearchObjectType.userProfile,
                objectId: 'user_new_photo',
                title: '新摄影师',
                subtitle: '同城影像',
                snippet: '同城影像创作',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadWireMap(<String, dynamic>{
                  'subAccountId': 'user_new_photo',
                  'username': 'user_new_photo',
                  'displayName': '新摄影师',
                  'headline': '同城影像',
                  'chatAvailable': false,
                  'relationshipCapability': <String, dynamic>{
                    'relationState': 'not_following',
                    'canFollow': true,
                    'canUnfollow': false,
                    'canOpenConversation': false,
                  },
                }),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
    }
    return const SearchResponse(
      request: SearchRequest(query: ''),
      sections: <SearchSection>[],
    );
  }
}

class _RecordingCanonicalSearchRepository implements SearchRepository {
  final List<SearchRequest> requests = <SearchRequest>[];
  final _FakeNetworkSearchRepository _delegate = _FakeNetworkSearchRepository();

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    requests.add(request.normalized());
    return _delegate.search(
      request,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

/// 交集消费契约 fake：内容命中携带云侧 connectionState 闭集与 intersectionReason
/// 子集（primaryText），用于验证端只读 primaryText、按 connectionState 分组、
/// 无 primaryText 不拼装交集句。
class _IntersectionContractSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (!normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    PostSearchItemView item(Map<String, dynamic> map) =>
        PostSearchItemView.fromMap(map);
    final connected = item(<String, dynamic>{
      'postId': 'post_connected_liked',
      'contentType': 'image',
      'contentIdentity': 'work',
      'title': '你点赞过的海边日落',
      'summary': '已互动内容',
      'coverUrl':
          'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?w=800',
      'authorDisplayName': '海边摄影师',
      'connectionState': 'connected',
      'likeCount': 42,
    });
    final leadWithPrimary = item(<String, dynamic>{
      'postId': 'post_lead_primary',
      'contentType': 'image',
      'contentIdentity': 'work',
      'title': '环岛路骑行机位合集',
      'summary': '交集线索内容',
      'coverUrl':
          'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800',
      'authorDisplayName': '骑行小林',
      'connectionState': 'intersection_lead',
      'intersectionReason': <String, dynamic>{
        'primaryText': '你关注的小林也在拍这里',
        'dimension': 'sharedFollowees',
        'intersectionClass': 'fact',
      },
    });
    final discoveryNoPrimary = item(<String, dynamic>{
      'postId': 'post_discovery_plain',
      'contentType': 'article',
      'contentIdentity': 'article',
      'title': '城市天际线拍摄攻略',
      'summary': '未连接且无交集句内容',
      'coverUrl':
          'https://images.unsplash.com/photo-1519046904884-53103b34b206?w=800',
      'authorDisplayName': '攻略君',
      'connectionState': 'unconnected',
    });
    return SearchResponse(
      request: normalized,
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: <SearchHit>[
            for (final view in <PostSearchItemView>[
              connected,
              leadWithPrimary,
              discoveryNoPrimary,
            ])
              SearchHit(
                objectType: SearchObjectType.contentPost,
                objectId: view.postId,
                title: view.title ?? view.postId,
                snippet: view.summary,
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadContentPost(view),
              ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

class _DegradedNetworkSearchRepository extends _FakeNetworkSearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final base = await super.search(request);
    return SearchResponse(
      request: base.request,
      sections: base.sections,
      degradeSignals: const <SearchDegradeSignal>[
        SearchDegradeSignal(
          code: 'circle_group_remote_empty',
          message: 'circle.group 远端返回空结果，准备回退本地快照。',
          objectType: SearchObjectType.circleGroup,
        ),
      ],
    );
  }
}

class _EmptyDegradedNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponse(
      request: request,
      sections: const <SearchSection>[],
      degradeSignals: const <SearchDegradeSignal>[
        SearchDegradeSignal(
          code: 'circle_group_remote_empty',
          message: 'circle.group 远端返回空结果，准备回退本地快照。',
          objectType: SearchObjectType.circleGroup,
        ),
      ],
    );
  }
}
