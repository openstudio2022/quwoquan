// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/local-chat-search-contract/spec.md#gwt-001
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import '../../../support/cloud_services/homepage_alpha_test_adapter.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_search_index.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/hybrid_search_repository.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';

import '../../../support/cloud_services/chat_repository_mock.dart';
import '../../../support/sqflite_ffi_test_support.dart';

const String _query = '契约摄影';
const String _canonicalResultTitle = '西湖晨光摄影测试详情';
const String _localContactTitle = '契约摄影师';
const String _localConversationTitle = '契约摄影交流群';

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  group('跨域搜索本地契约旅程', () {
    test('HybridSearch 仅在 suggest 合并本地聊天，result 保持 canonical Remote', () async {
      final canonical = _RecordingCanonicalSearchFacet(
        AlphaCanonicalSearchFacet(),
      );
      final harness = await _SearchJourneyHarness.create(
        canonicalSearch: canonical,
      );
      addTearDown(harness.dispose);
      final suggestion = await harness.searchRepository.search(
        SearchRequest(query: _query, mode: SearchMode.suggest),
      );
      final suggestionTitles = suggestion.sections
          .expand((section) => section.hits)
          .map((hit) => hit.title)
          .toSet();
      expect(suggestionTitles, contains(_localContactTitle));
      expect(suggestionTitles, contains(_localConversationTitle));

      final result = await harness.searchRepository.search(
        SearchRequest(query: _query, mode: SearchMode.result),
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

    testWidgets('SearchQuery 结构化失败展示重试，并在重试后恢复结果', (tester) async {
      _configureTestViewport(tester);
      final assistant = _FailOnceAssistantSearchFacet();
      final harness =
          await tester.runAsync(
            () => _SearchJourneyHarness.create(
              canonicalSearch: AlphaCanonicalSearchFacet(),
              assistantSearch: assistant,
            ),
          ) ??
          (throw TestFailure('无法创建搜索 local contract harness'));
      addTearDown(harness.dispose);

      await tester.pumpWidget(harness.buildResultsApp());
      await _pumpUntil(
        tester,
        find.byType(AppPageErrorState),
        reason: 'SearchQuery 失败后未展示结构化页面错误',
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
        reason: '重试后 SearchQuery 未恢复小趣结果',
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
  final AlphaSearchFeedbackWriter feedback;
  final MockChatRepository chatRepository;
  final AssistantXiaoquSearchFacet assistantSearch;

  static Future<_SearchJourneyHarness> create({
    required CanonicalSearchQueryFacet canonicalSearch,
    AssistantXiaoquSearchFacet? assistantSearch,
  }) async {
    final tempDirectory = Directory(
      '${Directory.systemTemp.path}/cross_domain_search_local_contract_'
      '${DateTime.now().microsecondsSinceEpoch}',
    );
    await tempDirectory.create(recursive: true);
    final store = LocalChatSearchStore(
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
    final alphaChatState = AlphaChatStateEngine();
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
      chatRepository: chatRepository,
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
      feedback: AlphaSearchFeedbackWriter(),
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
    final recentSearches = AlphaRecentSearchFacet();
    return ProviderScope(
      overrides: [
        searchRepositoryProvider.overrideWithValue(searchRepository),
        searchHotQueryReaderProvider.overrideWithValue(AlphaHotQueryReader()),
        recentSearchQueryProvider.overrideWithValue(recentSearches),
        recentSearchCommandWriterProvider.overrideWithValue(recentSearches),
        searchFeedbackCommandWriterProvider.overrideWithValue(feedback),
        assistantXiaoquSearchFacetProvider.overrideWithValue(assistantSearch),
        chatRepositoryCompositionProvider.overrideWithValue(chatRepository),
        circlesListQueryProvider.overrideWithValue(AlphaCircleQueryReader()),
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
    implements LocalCircleGroupSearchIndex {
  @override
  Future<bool> sync() async => true;

  @override
  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required String query,
    int limit = 20,
  }) async => const <LocalCircleGroupSnapshotRecord>[];
}

final class _RecordingCanonicalSearchFacet
    implements CanonicalSearchQueryFacet {
  _RecordingCanonicalSearchFacet(this._delegate);

  final CanonicalSearchQueryFacet _delegate;
  final List<CanonicalSearchQuery> requests = <CanonicalSearchQuery>[];

  @override
  Future<CanonicalSearchResult> search(
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

final class _FailOnceAssistantSearchFacet
    implements AssistantXiaoquSearchFacet {
  _FailOnceAssistantSearchFacet()
    : failure = CloudErrorMapper.fromStatusCode(
        503,
        requestPath: SearchApiMetadata.operationToPathTemplate['SearchQuery'],
      );

  final CloudException failure;
  int attempts = 0;

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    attempts += 1;
    if (attempts == 1) {
      throw failure;
    }
    return _assistantResult(query, searchIntensity);
  }
}

final class _AssistantSearchFacet implements AssistantXiaoquSearchFacet {
  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async => _assistantResult(query, searchIntensity);
}

AssistantSearchResultView _assistantResult(
  String query,
  SearchIntensity searchIntensity,
) => AssistantSearchResultView(
  queryEcho: query,
  summary: '$query 的小趣搜索结果',
  searchIntensity: searchIntensity,
  citations: const <AssistantSearchCitationView>[],
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
        action: BehaviorAction.onboardingInterest,
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
