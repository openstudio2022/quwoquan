// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/local-chat-search-contract/spec.md#gwt-001
import '../../../../../support/service/search_service/search/recent_search_state/recent_search_typed_double.dart';
import '../../../../../support/service/search_service/search/search_feedback_fact/search_feedback_typed_double.dart';
import '../../../../../support/service/search_service/search/search_index_view/canonical_search_typed_double.dart';
import '../../../../../support/service/search_service/search/search_request_fact/search_hot_query_typed_double.dart';
import '../../../../../support/runtime/platform/explicit_test_local_database_path_resolver.dart';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/canonical_search_query_facet.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_execution_values.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_group_local_search.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/runtime/di/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/hybrid_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/conversation_state_typed_double.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';

const String _query = '契约摄影';
const String _canonicalResultTitle = '西湖晨光摄影测试详情';
const String _localContactTitle = '契约摄影师';
const String _localConversationTitle = '契约摄影交流群';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('跨域搜索本地契约旅程', () {
    test('HybridSearch 仅在 suggest 合并本地聊天，result 保持 canonical Remote', () async {
      final canonical = _RecordingCanonicalSearchFacet(
        CanonicalSearchTypedDouble(),
      );
      final harness = await _SearchJourneyHarness.create(
        canonicalSearch: canonical,
      );
      addTearDown(harness.dispose);
      final suggestion = await harness.searchRepository.search(
        SearchRequest(query: _query, mode: CanonicalSearchMode.suggest),
      );
      final suggestionTitles = suggestion.sections
          .expand((section) => section.hits)
          .map((hit) => hit.title)
          .toSet();
      expect(suggestionTitles, contains(_localContactTitle));
      expect(suggestionTitles, contains(_localConversationTitle));

      final result = await harness.searchRepository.search(
        SearchRequest(query: _query, mode: CanonicalSearchMode.result),
      );
      final resultHits = result.sections
          .expand((section) => section.hits)
          .toList(growable: false);
      expect(
        resultHits.map((hit) => hit.title),
        contains(_canonicalResultTitle),
      );
      expect(
        resultHits.every(
          (hit) =>
              hit.resolvedFrom == SearchResolvedFrom.remote &&
              hit.objectType != SearchObjectType.chatContact &&
              hit.objectType != SearchObjectType.chatConversation &&
              hit.objectType != SearchObjectType.chatMessage,
        ),
        isTrue,
      );
      final resultRequests = canonical.requests
          .where(
            (request) =>
                request.query == _query &&
                request.mode == CanonicalSearchMode.result,
          )
          .toList(growable: false);
      expect(resultRequests, isNotEmpty);
      expect(
        resultRequests.expand((request) => request.objectTypes),
        isNot(
          contains(anyOf('chat_contact', 'chat_conversation', 'chat_message')),
        ),
      );
    });

    testWidgets('AssistantRun 结构化失败展示重试，并在重试后恢复结果', (tester) async {
      _configureTestViewport(tester);
      final assistant = _FailOnceAssistantSearchFacet();
      final harness =
          await tester.runAsync(
            () => _SearchJourneyHarness.create(
              canonicalSearch: CanonicalSearchTypedDouble(),
              assistantSearch: assistant,
            ),
          ) ??
          (throw TestFailure('无法创建搜索 local contract harness'));
      addTearDown(harness.dispose);

      await tester.pumpWidget(harness.buildResultsApp());
      await _pumpUntil(
        tester,
        find.byType(AppPageErrorState),
        reason: 'AssistantRun 失败后未展示结构化页面错误',
      );

      final errorState = tester.widget<AppPageErrorState>(
        find.byType(AppPageErrorState),
      );
      expect(
        errorState.semantic.sourceCode,
        assistant.failure.runtimeFailure.code,
      );
      expect(
        errorState.semantic.primaryAction?.type,
        anyOf(UiErrorActionType.retry, UiErrorActionType.resubmit),
      );
      expect(assistant.attempts, 1);

      await tester.tap(find.text(errorState.semantic.primaryAction!.label));
      await _pumpUntil(
        tester,
        find.text('$_query 的小趣搜索结果'),
        reason: '重试后 AssistantRun 未恢复小趣结果',
      );

      expect(assistant.attempts, 2);
      expect(find.byType(AppPageErrorState), findsNothing);
    });
  });
}

void _configureTestViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  required String reason,
  Duration timeout = const Duration(seconds: 8),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 50));
  }
  expect(finder, findsWidgets, reason: reason);
}

final class _SearchJourneyHarness {
  _SearchJourneyHarness._({
    required this.store,
    required this.tempDirectory,
    required this.searchRepository,
    required this.feedback,
    required this.chatRepository,
    required this.assistantSearch,
  });

  final LocalChatSearchStore store;
  final Directory tempDirectory;
  final HybridSearchRepository searchRepository;
  final SearchFeedbackTypedDouble feedback;
  final MockChatRepository chatRepository;
  final AssistantSearchRunFacade assistantSearch;

  static Future<_SearchJourneyHarness> create({
    required CanonicalSearchQueryFacet canonicalSearch,
    AssistantSearchRunFacade? assistantSearch,
  }) async {
    final tempDirectory = Directory(
      '${Directory.systemTemp.path}/cross_domain_search_local_contract_'
      '${DateTime.now().microsecondsSinceEpoch}',
    );
    await tempDirectory.create(recursive: true);
    final store = LocalChatSearchStore(
      databasePathResolver: const ExplicitTestLocalDatabasePathResolver(),
      databasePath: '${tempDirectory.path}/local_chat_search.db',
    );
    await store.ensureReady();

    final persona = ActivePersonaContextViewData.fallback(
      personaId: 'fixture_user_current',
      ownerUserId: 'fixture_user_current',
      subjectType: 'owner',
      displayName: '契约当前用户',
      avatarUrl: '',
      contextVersion: 1,
    );
    final alphaChatState = InMemoryChatStateEngine();
    final photoConversation = alphaChatState.conversationSeeds.singleWhere(
      (row) => row['id'] == 'fixture_conv_photo_group',
    );
    final chatRepository = MockChatRepository(
      seedConversations: <Map<String, dynamic>>[
        Map<String, dynamic>.from(photoConversation),
      ],
      seedMembers: <String, List<Map<String, dynamic>>>{
        'fixture_conv_photo_group': <Map<String, dynamic>>[],
      },
      seedMessages: <String, List<Map<String, dynamic>>>{
        'fixture_conv_photo_group': <Map<String, dynamic>>[],
      },
    );
    final sync = LocalChatSearchSyncService(
      contactRepository: chatRepository,
      conversationRepository: chatRepository,
      messageRepository: chatRepository,
      conversationCache: ConversationCacheService(),
      store: store,
      personaContextLoader: () async => persona,
      telemetrySink: const NoopCacheTelemetrySink(),
    );
    final synced = await sync.sync(force: true);
    if (!synced) {
      await store.close();
      await tempDirectory.delete(recursive: true);
      throw StateError('行为型 local contract 无法准备本地聊天搜索索引');
    }

    return _SearchJourneyHarness._(
      store: store,
      tempDirectory: tempDirectory,
      searchRepository: HybridSearchRepository(
        RemoteSearchRepository(
          remoteQuery: canonicalSearch,
          sessionIdProvider: () => 'search-session',
        ),
        store,
        sync,
        _EmptyCircleGroupSearchIndex(),
        () async => persona,
        const NoopCacheTelemetrySink(),
      ),
      feedback: SearchFeedbackTypedDouble(),
      chatRepository: chatRepository,
      assistantSearch: assistantSearch ?? _AssistantSearchFacet(),
    );
  }

  Widget buildResultsApp() => _buildScope(
    MaterialApp(
      home: SearchNetworkResultsPage(
        launchContext: _launchContext().copyWith(
          prefilledQuery: _query,
          initialNetworkTabId: 'xiaoqu',
        ),
      ),
    ),
  );

  Widget _buildScope(Widget child) {
    final recentSearches = RecentSearchTypedDouble();
    return ProviderScope(
      overrides: [
        searchRepositoryProvider.overrideWithValue(searchRepository),
        searchHotQueryReaderProvider.overrideWithValue(
          SearchHotQueryTypedDouble(),
        ),
        recentSearchQueryProvider.overrideWithValue(recentSearches),
        recentSearchCommandWriterProvider.overrideWithValue(recentSearches),
        searchFeedbackCommandWriterProvider.overrideWithValue(feedback),
        assistantSearchRunFacetProvider.overrideWithValue(assistantSearch),
        chatRepositoryCompositionProvider.overrideWithValue(chatRepository),
        circlesListQueryProvider.overrideWithValue(InMemoryCircleQueryReader()),
        homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
        behaviorRepositoryProvider.overrideWithValue(
          _RecordingBehaviorRepository(),
        ),
      ],
      child: child,
    );
  }

  Future<void> dispose() async {
    await store.close();
    if (await tempDirectory.exists()) {
      await tempDirectory.delete(recursive: true);
    }
  }
}

SearchLaunchContext _launchContext() => SearchLaunchContext(
  entrySurfaceId: AppUiSurfaces.globalSearchLanding.id,
  restoreState: false,
);

final class _EmptyCircleGroupSearchIndex
    implements CircleGroupLocalSearchIndex {
  @override
  Future<bool> sync() async => true;

  @override
  Future<List<CircleGroupLocalSearchHit>> searchGroups({
    required String query,
    int limit = 20,
  }) async => const <CircleGroupLocalSearchHit>[];
}

final class _RecordingCanonicalSearchFacet
    implements CanonicalSearchQueryFacet {
  _RecordingCanonicalSearchFacet(this._delegate);

  final CanonicalSearchQueryFacet _delegate;
  final List<CanonicalSearchQuery> requests = <CanonicalSearchQuery>[];

  @override
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    requests.add(query);
    return _delegate.search(
      query,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

final class _FailOnceAssistantSearchFacet implements AssistantSearchRunFacade {
  _FailOnceAssistantSearchFacet()
    : failure = CloudErrorMapper.fromStatusCode(
        503,
        requestPath: canonicalRemoteApiPath(
          AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
          pathParameters: const <String, String>{
            'sessionId': 'assistant-search-session',
          },
        ),
      );

  final CloudException failure;
  int attempts = 0;

  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    attempts += 1;
    if (attempts == 1) {
      throw failure;
    }
    return _assistantResult(query);
  }
}

final class _AssistantSearchFacet implements AssistantSearchRunFacade {
  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async => _assistantResult(query);
}

AssistantRunTerminalSnapshotView _assistantResult(String query) =>
    AssistantRunTerminalSnapshotView(
      answerText: '$query 的小趣搜索结果',
      processes: const <AssistantRunVisibleProcessView>[],
    );

final class _RecordingBehaviorRepository extends BehaviorRepository {
  final List<BehaviorEvent> events = <BehaviorEvent>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    this.events.addAll(events);
  }

  @override
  Future<void> submitOnboardingInterest({
    required String clientEventId,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    events.add(
      BehaviorEvent(
        contentId: '',
        action: BehaviorEventType.onboardingInterest,
        clientEventId: clientEventId,
        taxonomyReleaseId: taxonomyReleaseId,
        tags: tagRefs,
      ),
    );
  }

  @override
  Future<void> clearPendingForLogout() async {
    events.clear();
  }
}
