import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:hive/hive.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_send_outbox.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_send_provider.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/cloud_services/user_typed_facet_test_support.dart';
import '../../../support/fixtures/chat/chat_mock_seed_refs.dart';
import '../../../support/fixtures/chat/fixture_realtime_connection_delegate.dart';

Widget _buildApp() {
  final repo = MockChatRepository(
    seedConversations: <Map<String, dynamic>>[
      chatConversationSeedById('fixture_conv_direct'),
      chatConversationSeedById('fixture_conv_group'),
    ],
  );
  return ProviderScope(
    overrides: [
      realtimeConnectionManagerProvider.overrideWith(
        () => RealtimeConnectionNotifier(
          delegateFactory:
              ({
                required ref,
                required onStateChanged,
                required currentUserIdResolver,
              }) => FixtureRealtimeConnectionDelegate(
                read: ref.read,
                invalidate: ref.invalidate,
                onStateChanged: onStateChanged,
              ),
        ),
      ),
      chatRepositoryCompositionProvider.overrideWithValue(repo),
      greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        mutualRelationshipCapabilityRepository(),
      ),
      searchRepositoryProvider.overrideWithValue(_FakeSearchRepository()),
      assistantXiaoquSearchFacetProvider.overrideWithValue(
        _NoopAssistantXiaoquSearchFacet(),
      ),
      voiceQueuedSenderProvider.overrideWithValue(
        (_, _) async => VoiceSendStatus.completed,
      ),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: AppRoutePaths.chat,
        observers: <NavigatorObserver>[chatRouteObserver],
        routes: [
          GoRoute(
            path: AppRoutePaths.chat,
            builder: (_, _) => const Scaffold(body: ChatPage()),
          ),
          GoRoute(
            path: AppRoutePaths.globalSearch,
            builder: (_, state) {
              final launchContext = state.extra is SearchLaunchContext
                  ? state.extra! as SearchLaunchContext
                  : const SearchLaunchContext(
                      entrySurfaceId: AppRoutePaths.chat,
                    );
              return GlobalSearchPage(launchContext: launchContext);
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatDetailPathTemplate.replaceAll(
              '{id}',
              ':id',
            ),
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return ChatConversationPage(
                conversationId: id,
                onBack: () {
                  if (context.canPop()) {
                    context.pop();
                  } else {
                    context.go(AppRoutePaths.chat);
                  }
                },
              );
            },
          ),
        ],
      ),
    ),
  );
}

void _suppressNonCriticalFlutterErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
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

Future<void> _disposeJourneyApp(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    Hive.init(
      '${Directory.systemTemp.path}/qwq_chat_search_navigation_${DateTime.now().microsecondsSinceEpoch}',
    );
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
  });

  testWidgets('消息页经聊天记录联想直达会话并返回后可再进入另一会话', (tester) async {
    _suppressNonCriticalFlutterErrors();
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.byType(ChatPage), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.globalSearchLauncherButton));
    await tester.pumpAndSettle();

    expect(find.byType(GlobalSearchPage), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '群',
    );
    await tester.pump(const Duration(milliseconds: 220));
    await tester.pumpAndSettle();

    // 联想区聊天记录已收敛为直达 tile（去除「更多聊天记录」see-more 按钮），
    // 命中的会话直接点击即可进入对应会话。
    final firstConversation = find.text('周末登山群').first;
    await tester.ensureVisible(firstConversation);
    await tester.pumpAndSettle();
    await tester.tap(firstConversation);
    await tester.pumpAndSettle();
    await _pumpUntil(
      tester,
      condition: () =>
          tester.container().read(realtimeConnectionManagerProvider) ==
          TransportState.active,
    );

    expect(find.byType(ChatConversationPage), findsOneWidget);
    expect(
      tester
          .widget<ChatConversationPage>(find.byType(ChatConversationPage))
          .conversationId,
      'conv_002',
    );
    expect(tester.takeException(), isNull);

    final detailContext = tester.element(find.byType(ChatConversationPage));
    Navigator.of(detailContext).pop();
    await tester.pumpAndSettle();
    await _pumpUntil(
      tester,
      condition: () =>
          tester.container().read(realtimeConnectionManagerProvider) ==
          TransportState.idle,
    );

    expect(find.byType(GlobalSearchPage), findsOneWidget);
    expect(tester.takeException(), isNull);

    final searchContext = tester.element(find.byType(GlobalSearchPage));
    Navigator.of(searchContext).pop();
    await tester.pumpAndSettle();

    expect(find.byType(ChatPage), findsOneWidget);
    expect(tester.takeException(), isNull);

    await _pumpUntil(
      tester,
      condition: () => find.text('李明').evaluate().isNotEmpty,
    );
    final inboxRow = find.ancestor(
      of: find.text('李明').first,
      matching: find.byKey(const ValueKey<String>('chat-inbox-row-conv_001')),
    );
    await tester.ensureVisible(inboxRow);
    await tester.pumpAndSettle();
    await tester.tap(inboxRow);
    await tester.pumpAndSettle();
    await _pumpUntil(
      tester,
      condition: () =>
          tester.container().read(realtimeConnectionManagerProvider) ==
          TransportState.active,
    );

    expect(find.byType(ChatConversationPage), findsOneWidget);
    expect(
      tester
          .widget<ChatConversationPage>(find.byType(ChatConversationPage))
          .conversationId,
      'conv_001',
    );
    expect(tester.takeException(), isNull);

    final secondDetailContext = tester.element(
      find.byType(ChatConversationPage),
    );
    Navigator.of(secondDetailContext).pop();
    await tester.pumpAndSettle();
    await _pumpUntil(
      tester,
      condition: () =>
          tester.container().read(realtimeConnectionManagerProvider) ==
          TransportState.idle,
    );
    expect(find.byType(ChatPage), findsOneWidget);

    await _disposeJourneyApp(tester);
  });
}

class _FakeSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode != SearchMode.suggest || normalized.query != '群') {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    return SearchResponse(
      request: normalized,
      sections: const <SearchSection>[
        SearchSection(
          id: 'chat_records',
          title: '聊天记录',
          objectTypes: <SearchObjectType>[SearchObjectType.chatConversation],
          resolvedFrom: SearchResolvedFrom.local,
          hits: <SearchHit>[
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
          ],
        ),
      ],
    );
  }
}

class _NoopAssistantXiaoquSearchFacet implements AssistantXiaoquSearchFacet {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
