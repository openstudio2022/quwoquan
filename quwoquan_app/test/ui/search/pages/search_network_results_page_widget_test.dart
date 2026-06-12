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
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_summary_card.dart';
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
  testWidgets('网络结果页按方案 B 默认综合并展示圈子频道分类', (tester) async {
    await tester.pumpWidget(
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
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('小趣搜'), findsOneWidget);
    expect(find.text('综合'), findsWidgets);
    expect(
      tester.getTopLeft(find.text('小趣搜')).dx,
      lessThan(tester.getTopLeft(find.text('综合').first).dx),
    );
    expect(find.text('主页'), findsOneWidget);
    expect(find.text('消息'), findsWidgets);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('文章'), findsOneWidget);
    expect(find.text('内容'), findsWidgets);
    expect(find.text('推荐'), findsNothing);
    expect(find.text('遇见'), findsNothing);
    expect(find.text('位置'), findsNothing);
    const businessLabels = <String>['校园', '旅行', '摄影', '科技', '车之家'];
    final tabBar = tester.widget<SecondaryCapsuleTabBar>(
      find.byType(SecondaryCapsuleTabBar),
    );
    expect(
      tabBar.tabs.sublist(tabBar.tabs.length - businessLabels.length),
      businessLabels,
    );
    for (final removed in <String>['人文', '生活', '运动', '美食', '车友']) {
      expect(find.text(removed), findsNothing);
    }
    expect(find.textContaining('小趣正在整理'), findsNothing);
  });

  testWidgets('切换频道后展示对应分类结果', (tester) async {
    await tester.pumpWidget(
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

    await tester.tap(find.text('摄影'));
    await tester.pumpAndSettle();

    expect(find.textContaining('摄影'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
  });

  testWidgets('主页 tab 可展示共享主页结果', (tester) async {
    // mock fixture 含多条「西湖」主页，放大视口避免目标卡被列表懒加载裁剪。
    tester.view.physicalSize = const Size(1080, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
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

    expect(find.text('主页'), findsOneWidget);
    expect(find.text('西湖景区'), findsWidgets);
    expect(find.textContaining('共享主页并进入详情'), findsOneWidget);
    expect(find.byType(HomepageSummaryCard), findsWidgets);
  });

  testWidgets('综合 tab 汇总圈子与群组结果', (tester) async {
    await tester.pumpWidget(
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
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(seconds: 3));

    expect(find.text('综合'), findsWidgets);
    expect(find.text('光影摄影社主群'), findsWidgets);
    expect(find.byType(PostPreviewListTile), findsWidgets);
  });

  testWidgets('消息 tab 可展示聊天搜索结果', (tester) async {
    await tester.pumpWidget(
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
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('消息'), findsWidgets);
    expect(find.text('西湖摄影讨论'), findsWidgets);
  });

  testWidgets('小趣 tab 可作为初始 tab 打开', (tester) async {
    await tester.pumpWidget(
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

    expect(find.text('小趣搜'), findsWidgets);
    expect(find.textContaining('正在为你整理'), findsWidgets);
  });

  testWidgets('不存在的 locations tab 归一到综合避免空 tab 漂移', (tester) async {
    await tester.pumpWidget(
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
    expect(tabBar.tabs[tabBar.activeIndex], '综合');
  });

  testWidgets('degrade signal 可在结果页展示', (tester) async {
    await tester.pumpWidget(
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'groups',
        ),
        repository: _DegradedNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.textContaining('部分结果已降级'), findsOneWidget);
  });

  testWidgets('内容类型筛选可驱动网络结果页加载指定内容结果', (tester) async {
    await tester.pumpWidget(
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

    expect(find.text('街头摄影'), findsWidgets);
  });
}

class _FakeNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(SearchRequest request) async {
    final normalized = request.normalized();
    if (normalized.objectTypes.contains(SearchObjectType.contentPost)) {
      final item = PostSearchItemView.fromMap(<String, dynamic>{
        'postId': 'fake_street_photo',
        'contentType': 'image',
        'contentIdentity': 'work',
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
            title: '群组',
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
                  'circleId': 'circle_photo_01',
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
