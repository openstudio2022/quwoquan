import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_repository_mock.dart';
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
      chatRepositoryProvider.overrideWithValue(MockChatRepository()),
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
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await const MockUserProfileRepository().clearRecentSearches();
  });

  testWidgets('默认页固定 Tab 与结果页一致且空历史隐藏最近搜索', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('小趣'), findsOneWidget);
    expect(find.text('全部'), findsWidgets);
    expect(find.text('交集'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('长文'), findsOneWidget);
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

    SharedPreferences.setMockInitialValues(<String, Object>{
      'global_search_recent_entries_v1': jsonEncode(<Map<String, dynamic>>[
        _historyEntry('摄影圈'),
        _historyEntry('旅行手账'),
        _historyEntry('李明'),
        _historyEntry('周末登山'),
        _historyEntry('咖啡俱乐部'),
        _historyEntry('夜景延时'),
        _historyEntry('圈子搭子'),
        _historyEntry('厦门大学'),
        _historyEntry('鼓浪屿'),
        _historyEntry('九寨沟'),
        _historyEntry('环岛路'),
        _historyEntry('旅行'),
        _historyEntry('武夷山'),
        _historyEntry('黄山'),
        _historyEntry('西湖'),
      ]),
    });

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

  testWidgets('输入关键词后展示实时联想联系人与推荐搜索', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '李',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    expect(find.text('推荐搜索'), findsOneWidget);
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

  testWidgets('联系人没有单聊时回退到已存在讨论会话', (tester) async {
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
            payload: SearchHitPayloadWireMap(<String, dynamic>{
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
        payload: SearchHitPayloadWireMap(<String, dynamic>{
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
        payload: SearchHitPayloadWireMap(<String, dynamic>{
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
        payload: SearchHitPayloadWireMap(<String, dynamic>{
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
        payload: SearchHitPayloadWireMap(<String, dynamic>{
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
    Map<String, dynamic>? contextSnapshot,
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
