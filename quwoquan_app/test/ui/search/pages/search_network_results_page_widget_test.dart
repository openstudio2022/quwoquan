import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tabs_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';

/// 与 [circles_page_widget_test] 同源：避免单测里 [CircleCategoryTabsLoader.loadFromAsset] 走 rootBundle 失败或挂起。
Map<String, CircleCategoryTabConfigDto> _searchNetworkCategoryTabsFixture() {
  final candidates = <File>[
    File(
      '${Directory.current.path}/../quwoquan_service/contracts/metadata/social/circle/ui_category_tabs.yaml',
    ),
    File(
      '${Directory.current.path}/quwoquan_service/contracts/metadata/social/circle/ui_category_tabs.yaml',
    ),
  ];
  for (final f in candidates) {
    if (f.existsSync()) {
      return CircleCategoryTabsLoader.parseFromYamlString(f.readAsStringSync());
    }
  }
  return Map<String, CircleCategoryTabConfigDto>.from(
    CircleCategoryTabDefaults.remoteStyleFallback,
  );
}

class _SearchNetworkCategoryFixtureRepo extends MockCircleRepository {
  @override
  Future<Map<String, CircleCategoryTabConfigDto>>
  getCircleCategoryConfig() async {
    return _searchNetworkCategoryTabsFixture();
  }
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
    prefilledQuery: '影',
    initialNetworkTabId: 'all',
  ),
}) {
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(
        _SearchNetworkCategoryFixtureRepo(),
      ),
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
      circleRepositoryProvider.overrideWithValue(
        _SearchNetworkCategoryFixtureRepo(),
      ),
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
      condition: () => find.textContaining('发现区').evaluate().isNotEmpty,
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
    expect(find.textContaining('已加入圈子'), findsWidgets);
    expect(find.textContaining('发现区'), findsWidgets);
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
      condition: () => find.text('光影摄影社主群').evaluate().isNotEmpty,
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
      condition: () => find.text('西湖摄影讨论').evaluate().isNotEmpty,
    );

    expect(find.text('西湖摄影讨论'), findsOneWidget);
  });

  testWidgets('切换交集后展示概览和交集发现流', (tester) async {
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
    await tester.pumpAndSettle();

    await tester.tap(find.text('交集'));
    await _pumpUntil(
      tester,
      condition: () => find.text('共同兴趣').evaluate().isNotEmpty,
    );

    expect(find.text('共同兴趣'), findsOneWidget);
    expect(find.textContaining('感兴趣圈子'), findsWidgets);
    expect(find.textContaining('交集发现流'), findsWidgets);
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

  testWidgets('全部 tab 汇总已连接区和发现区', (tester) async {
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
      condition: () => find.text('光影摄影社主群').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.textContaining('聊天记录'), findsWidgets);
    expect(find.text('光影摄影社主群'), findsWidgets);
    expect(find.textContaining('发现区'), findsWidgets);
  });

  testWidgets('旧消息 tab 深链归一到全部并展示聊天结果', (tester) async {
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
      condition: () => find.text('西湖摄影讨论').evaluate().isNotEmpty,
    );

    expect(find.text('全部'), findsWidgets);
    expect(find.text('西湖摄影讨论'), findsWidgets);
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

  testWidgets('degrade signal 可在结果页展示', (tester) async {
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

    expect(find.textContaining('部分结果已降级'), findsOneWidget);
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
  Future<SearchResponse> search(SearchRequest request) async {
    final normalized = request.normalized();
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
        'circleName': '摄影影像',
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
                subtitle: item.circleName,
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
    if (normalized.objectTypes.contains(
      SearchObjectType.integrationLocationPoi,
    )) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[
          SearchSection(
            id: 'locations',
            title: '地点',
            objectTypes: <SearchObjectType>[
              SearchObjectType.integrationLocationPoi,
            ],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.integrationLocationPoi,
                objectId: 'poi_west_lake',
                title: '西湖',
                subtitle: '杭州',
                snippet: '12个交集',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadWireMap(<String, dynamic>{
                  'id': 'poi_west_lake',
                  'name': '西湖',
                  'address': '浙江省杭州市西湖区',
                }),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        ],
      );
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
                snippet: '共同兴趣 3 个',
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
                snippet: '共同兴趣 1 个',
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

class _DegradedNetworkSearchRepository extends _FakeNetworkSearchRepository {
  @override
  Future<SearchResponse> search(SearchRequest request) async {
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
