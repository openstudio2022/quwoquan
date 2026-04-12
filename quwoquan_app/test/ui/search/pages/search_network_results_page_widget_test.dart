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
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/models/search_hit_payload.dart';
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
  Future<Map<String, CircleCategoryTabConfigDto>> getCircleCategoryConfig() async {
    return _searchNetworkCategoryTabsFixture();
  }
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
    prefilledQuery: '影',
    initialNetworkTabId: 'xiaoqu',
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
  testWidgets('网络结果页展示小趣搜和圈子频道分类', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('小趣搜'), findsWidgets);
    expect(find.text('推荐'), findsOneWidget);
    expect(find.text('人文'), findsOneWidget);
    expect(find.textContaining('正在为你整理'), findsOneWidget);
  });

  testWidgets('切换频道后展示对应分类结果', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pump();
    await tester.pumpAndSettle();

    await tester.tap(find.text('人文'));
    await tester.pumpAndSettle();

    expect(find.textContaining('人文'), findsWidgets);
    expect(find.text('街头摄影'), findsWidgets);
  });

  testWidgets('主页 tab 可展示共享主页结果', (tester) async {
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

  testWidgets('群组 tab 可展示圈子与群组结果', (tester) async {
    await tester.pumpWidget(
      _buildAppWithSearchRepository(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: '光影',
          initialNetworkTabId: 'groups',
        ),
        repository: _FakeNetworkSearchRepository(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(seconds: 3));

    expect(find.text('群组'), findsWidgets);
    expect(find.text('没有找到相关群组'), findsNothing);
    expect(find.byType(PostPreviewListTile), findsWidgets);
  });

  testWidgets('位置 tab 可展示 integration location 结果', (tester) async {
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
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('位置'), findsWidgets);
    expect(find.text('西湖风景名胜区'), findsWidgets);
  });

  testWidgets('内容类型筛选可驱动网络结果页加载指定内容结果', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        launchContext: const SearchLaunchContext(
          entrySurfaceId: '/search',
          prefilledQuery: 'UI',
          initialNetworkTabId: 'all',
          searchObjectSelection: SearchObjectSelection(
            contentTypes: <SearchContentTypeFilter>{
              SearchContentTypeFilter.article,
            },
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('UI设计的心理学原理：色彩、布局与用户认知'), findsWidgets);
  });
}

class _FakeNetworkSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(SearchRequest request) async {
    final normalized = request.normalized();
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
                payload: const SearchHitPayloadLegacy(<String, dynamic>{
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
    if (normalized.objectTypes.contains(
      SearchObjectType.integrationLocationPoi,
    )) {
      return SearchResponse(
        request: normalized,
        sections: <SearchSection>[
          SearchSection(
            id: 'locations',
            title: '位置',
            objectTypes: const <SearchObjectType>[
              SearchObjectType.integrationLocationPoi,
            ],
            hits: const <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.integrationLocationPoi,
                objectId: 'poi_west_lake',
                title: '西湖风景名胜区',
                subtitle: '杭州市西湖区龙井路1号',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: const SearchHitPayloadLegacy(<String, dynamic>{
                  'id': 'poi_west_lake',
                  'name': '西湖风景名胜区',
                  'latitude': 30.2431,
                  'longitude': 120.1500,
                  'address': '杭州市西湖区龙井路1号',
                  'distanceMeters': 1200,
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
