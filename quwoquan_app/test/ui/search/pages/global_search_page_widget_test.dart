import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
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
    overrides: [
      searchRepositoryProvider.overrideWithValue(_FakeSearchRepository()),
      assistantRepositoryProvider.overrideWithValue(_FakeAssistantRepository()),
    ],
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

  testWidgets('无记录记录时隐藏最近搜索区块', (tester) async {
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

    final liXiangButton = find.ancestor(
      of: find.text('李想').last,
      matching: find.byType(CupertinoButton),
    );
    await tester.ensureVisible(liXiangButton.first);
    tester.widget<CupertinoButton>(liXiangButton.first).onPressed!.call();
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
    await _pumpUntil(
      tester,
      condition: () => find.text('王芳').evaluate().isNotEmpty,
    );

    await tester.tap(find.text('王芳').last);
    await _pumpUntil(
      tester,
      condition: () => find.text('chat:conv_002').evaluate().isNotEmpty,
    );

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
    await _pumpUntil(
      tester,
      condition: () => find.text('冰 相关主页').evaluate().isNotEmpty,
    );

    await tester.tap(find.text('冰').last);
    await _pumpUntil(
      tester,
      condition: () => find.text('小趣搜').evaluate().isNotEmpty,
    );

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
    await _pumpUntil(
      tester,
      condition: () => find.text('西湖 相关主页').evaluate().isNotEmpty,
    );

    expect(find.text('西湖 相关主页'), findsOneWidget);

    await tester.tap(find.text('西湖 相关主页'));
    await _pumpUntil(
      tester,
      condition: () => find.text('主页').evaluate().isNotEmpty,
    );

    expect(
      find.byKey(const ValueKey<String>('network_results_homepages')),
      findsOneWidget,
    );
    expect(find.text('西湖景区'), findsWidgets);
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
  Future<SearchResponse> search(SearchRequest request) async {
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
          payload: const SearchHitPayloadWireMap(<String, dynamic>{
            'homepageId': 'homepage_west_lake',
            'homepageType': 'place',
            'title': '西湖景区',
            'subtitle': '杭州西湖风景名胜区',
            'city': '杭州',
            'address': '浙江省杭州市西湖区',
          }),
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
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_li_ming',
              'displayName': '李明',
              'conversationId': 'conv_001',
            }),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_xiang',
            title: '李想',
            resolvedFrom: SearchResolvedFrom.local,
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_li_xiang',
              'displayName': '李想',
              'conversationId': 'conv_007',
            }),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_qing',
            title: '李青',
            resolvedFrom: SearchResolvedFrom.local,
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_li_qing',
              'displayName': '李青',
              'conversationId': 'conv_008',
            }),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_yue',
            title: '李悦',
            resolvedFrom: SearchResolvedFrom.local,
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_li_yue',
              'displayName': '李悦',
              'conversationId': 'conv_009',
            }),
          ),
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_li_ze',
            title: '李泽',
            resolvedFrom: SearchResolvedFrom.local,
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_li_ze',
              'displayName': '李泽',
              'conversationId': 'conv_010',
            }),
          ),
        ];
      case '王':
        return const <SearchHit>[
          SearchHit(
            objectType: SearchObjectType.chatContact,
            objectId: 'user_wang_fang',
            title: '王芳',
            resolvedFrom: SearchResolvedFrom.local,
            payload: const SearchHitPayloadWireMap(<String, dynamic>{
              'contactId': 'user_wang_fang',
              'displayName': '王芳',
              'conversationId': 'conv_002',
            }),
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
        payload: const SearchHitPayloadWireMap(<String, dynamic>{
          'conversationId': 'conv_002',
          'type': 'group',
          'title': '周末登山群',
          'memberCount': 15,
          'lastMessagePreview': '周六早上8点出发',
        }),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_3',
        title: '3人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: const SearchHitPayloadWireMap(<String, dynamic>{
          'conversationId': 'conv_grid_3',
          'type': 'group',
          'title': '3人测试群',
          'memberCount': 3,
          'lastMessagePreview': '测试群聊',
        }),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_4',
        title: '4人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: const SearchHitPayloadWireMap(<String, dynamic>{
          'conversationId': 'conv_grid_4',
          'type': 'group',
          'title': '4人测试群',
          'memberCount': 4,
          'lastMessagePreview': '测试群聊',
        }),
      ),
      SearchHit(
        objectType: SearchObjectType.chatConversation,
        objectId: 'conv_grid_5',
        title: '5人测试群',
        resolvedFrom: SearchResolvedFrom.local,
        payload: const SearchHitPayloadWireMap(<String, dynamic>{
          'conversationId': 'conv_grid_5',
          'type': 'group',
          'title': '5人测试群',
          'memberCount': 5,
          'lastMessagePreview': '测试群聊',
        }),
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

class _FakeAssistantRepository implements AssistantRepository {
  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async => AssistantPolicyView(
    version: policyVersionHint.isEmpty ? 'test' : policyVersionHint,
    values: <String, dynamic>{'grantedScopes': const <String>[]},
  );

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async => AssistantInteractionReportBatchAck(
    accepted: true,
    count: events.length,
    resource: 'interaction_event_batch',
  );

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async => AssistantScorecardReportBatchAck(
    accepted: true,
    count: scorecards.length,
    resource: 'scorecard_batch',
  );

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    return AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime(2026, 3, 27),
    );
  }

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    return const <AssistantSkillConsent>[];
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {}

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) async {
    return AssistantSearchResultView(
      queryEcho: query,
      summary: '$query 的推荐结果',
      searchIntensity: searchIntensity,
      citations: const <AssistantSearchCitationView>[
        AssistantSearchCitationView(
          citationId: 'citation_1',
          objectType: 'content.post',
          objectId: 'post_1',
          title: '冰雪旅行推荐',
          snippet: '适合冬季出行的内容推荐',
          sourceDomain: '小趣搜',
        ),
      ],
    );
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = 32,
    String? status,
  }) async => const <AssistantUserTaskView>[];

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = 32,
  }) async => const <AssistantUserMemoryView>[];

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = 64,
  }) async => const <AssistantSkillCatalogItemView>[];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Map<String, dynamic> _historyEntry(String query) {
  return <String, dynamic>{
    'entryId': query,
    'query': query,
    'scope': SearchScope.all.wireValue,
    'updatedAt': DateTime(2026, 3, 22, 10).toIso8601String(),
  };
}
