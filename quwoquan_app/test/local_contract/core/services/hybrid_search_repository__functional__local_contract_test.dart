// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/spec.md#sit-001
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/local-chat-search-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/circle-group-hybrid-fallback-contract/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_search_index.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/hybrid_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('suggest 合并 canonical Remote 与账号隔离本地命中', () async {
    final remote = _RecordingRemoteRepository();
    final local = _LocalReader();
    final sync = _SyncSpy();
    final circleGroups = _CircleGroupIndexSpy();
    final telemetry = _TelemetrySpy();
    final repository = HybridSearchRepository(
      remote,
      local,
      sync,
      circleGroups,
      _personaContext,
      telemetry,
    );

    final response = await repository.search(
      const SearchRequest(
        query: '摄影',
        mode: SearchMode.suggest,
        objectTypes: <SearchObjectType>{
          SearchObjectType.contentPost,
          SearchObjectType.chatContact,
          SearchObjectType.chatConversation,
          SearchObjectType.chatMessage,
          SearchObjectType.circleGroup,
        },
      ),
    );

    expect(remote.calls, 1);
    expect(sync.calls, 1);
    expect(circleGroups.syncCalls, 1);
    expect(circleGroups.searchCalls, 1);
    expect(
      local.calls,
      containsAll(<String>['contacts', 'conversations', 'messages']),
    );
    expect(
      response.hits.map((hit) => hit.objectType),
      containsAll(<SearchObjectType>[
        SearchObjectType.contentPost,
        SearchObjectType.chatContact,
        SearchObjectType.chatConversation,
        SearchObjectType.chatMessage,
        SearchObjectType.circleGroup,
      ]),
    );
    final groupHits = response.hits
        .where((hit) => hit.objectType == SearchObjectType.circleGroup)
        .toList(growable: false);
    expect(groupHits.map((hit) => hit.objectId), contains('group-remote'));
    expect(
      groupHits.map((hit) => hit.objectId),
      isNot(contains('group-photo')),
    );
    expect(
      groupHits.every((hit) => hit.resolvedFrom == SearchResolvedFrom.remote),
      isTrue,
    );
    expect(response.degradeSignals, isEmpty);
    expect(telemetry.events, isEmpty);
  });

  test('result 严格只走 canonical Remote，不读取本地命名空间', () async {
    final remote = _RecordingRemoteRepository();
    final local = _LocalReader();
    final sync = _SyncSpy();
    final circleGroups = _CircleGroupIndexSpy();
    final repository = HybridSearchRepository(
      remote,
      local,
      sync,
      circleGroups,
      _personaContext,
      _TelemetrySpy(),
    );

    final response = await repository.search(
      const SearchRequest(query: '西湖', mode: SearchMode.result),
    );

    expect(response.hits, hasLength(1));
    expect(remote.calls, 1);
    expect(sync.calls, 0);
    expect(circleGroups.syncCalls, 0);
    expect(circleGroups.searchCalls, 0);
    expect(local.calls, isEmpty);
  });

  test('suggest 后台索引同步失败会记录降级且不产生未处理异常', () async {
    final telemetry = _TelemetrySpy();
    final repository = HybridSearchRepository(
      _RecordingRemoteRepository(),
      _LocalReader(),
      _SyncSpy(failure: StateError('sync unavailable')),
      _CircleGroupIndexSpy(),
      _personaContext,
      telemetry,
    );

    final response = await repository.search(
      const SearchRequest(
        query: '摄影',
        mode: SearchMode.suggest,
        objectTypes: <SearchObjectType>{SearchObjectType.chatContact},
      ),
    );
    await Future<void>.delayed(Duration.zero);

    expect(response.hits, isNotEmpty);
    expect(telemetry.events, contains('search_hybrid_degraded'));
  });

  test('suggest 同步返回 false 时记录 typed degrade telemetry', () async {
    final telemetry = _TelemetrySpy();
    final repository = HybridSearchRepository(
      _RecordingRemoteRepository(),
      _LocalReader(),
      _SyncSpy(result: false),
      _CircleGroupIndexSpy(),
      _personaContext,
      telemetry,
    );

    await repository.search(
      const SearchRequest(
        query: '摄影',
        mode: SearchMode.suggest,
        objectTypes: <SearchObjectType>{SearchObjectType.chatContact},
      ),
    );
    await Future<void>.delayed(Duration.zero);

    expect(telemetry.events, contains('search_hybrid_degraded'));
  });

  test('Remote suggest 不可用时仅本地讨论标记 typed local_fallback', () async {
    final telemetry = _TelemetrySpy();
    final repository = HybridSearchRepository(
      _RecordingRemoteRepository(failure: StateError('remote unavailable')),
      _LocalReader(),
      _SyncSpy(),
      _CircleGroupIndexSpy(),
      _personaContext,
      telemetry,
    );

    final response = await repository.search(
      const SearchRequest(
        query: '摄影',
        mode: SearchMode.suggest,
        objectTypes: <SearchObjectType>{
          SearchObjectType.chatContact,
          SearchObjectType.circleGroup,
        },
      ),
    );

    expect(response.degradeSignals.map((signal) => signal.code), <String>[
      'search_cloud_suggest_unavailable',
    ]);
    expect(response.sections, hasLength(2));
    final contactsSection = response.sections.singleWhere(
      (section) => section.id == 'contacts',
    );
    final groupsSection = response.sections.singleWhere(
      (section) => section.id == 'groups',
    );
    expect(contactsSection.resolvedFrom, SearchResolvedFrom.local);
    expect(groupsSection.resolvedFrom, SearchResolvedFrom.localFallback);
    final groupHit = groupsSection.hits.single;
    expect(groupHit.objectType, SearchObjectType.circleGroup);
    expect(groupHit.resolvedFrom, SearchResolvedFrom.localFallback);
    expect(groupHit.objectId, 'group-photo');
    expect(groupHit.asCircleGroupItem?.circleId, 'circle-photo');
    expect(groupHit.asCircleGroupItem?.circleName, '契约摄影社');
    expect(telemetry.events, contains('search_hybrid_degraded'));
  });
}

Future<ActivePersonaContextViewData> _personaContext() async {
  return const ActivePersonaContextViewData(
    subAccountId: 'persona-1',
    ownerUserId: 'owner-1',
    subjectType: 'persona',
    displayName: '测试用户',
    avatarUrl: '',
    contextVersion: 1,
  );
}

final class _RecordingRemoteRepository implements SearchRepository {
  _RecordingRemoteRepository({this.failure});

  final Object? failure;
  int calls = 0;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    calls += 1;
    if (failure != null) {
      throw failure!;
    }
    final normalized = request.normalized();
    return SearchResponse(
      request: normalized,
      searchRequestId: 'search.req.hybrid',
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: const <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post-1',
              title: '摄影内容',
              resolvedFrom: SearchResolvedFrom.remote,
            ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        if (normalized.objectTypes.contains(SearchObjectType.circleGroup))
          const SearchSection(
            id: 'groups',
            title: '讨论',
            objectTypes: <SearchObjectType>[SearchObjectType.circleGroup],
            hits: <SearchHit>[
              SearchHit(
                objectType: SearchObjectType.circleGroup,
                objectId: 'group-remote',
                title: '云侧摄影讨论',
                resolvedFrom: SearchResolvedFrom.remote,
                payload: SearchHitPayloadCircleGroup(
                  CircleSearchItemView(
                    circleId: 'circle-remote',
                    name: '云侧摄影讨论',
                    memberCount: 12,
                    postCount: 3,
                  ),
                ),
              ),
            ],
            resolvedFrom: SearchResolvedFrom.remote,
          ),
      ],
    );
  }
}

final class _CircleGroupIndexSpy implements LocalCircleGroupSearchIndex {
  int syncCalls = 0;
  int searchCalls = 0;

  @override
  Future<bool> sync() async {
    syncCalls += 1;
    return true;
  }

  @override
  Future<List<LocalCircleGroupSnapshotRecord>> searchGroups({
    required String query,
    int limit = 20,
  }) async {
    searchCalls += 1;
    return const <LocalCircleGroupSnapshotRecord>[
      LocalCircleGroupSnapshotRecord(
        groupId: 'group-photo',
        circleId: 'circle-photo',
        name: '契约摄影群',
        description: '摄影讨论',
        circleName: '契约摄影社',
        groupType: 'public_group',
        visibility: 'public',
        conversationId: 'conversation-photo',
        memberCount: 8,
        updatedAt: '2026-07-24T00:00:00.000Z',
      ),
    ];
  }
}

final class _LocalReader implements LocalChatSearchReader {
  final List<String> calls = <String>[];

  @override
  Future<List<LocalChatSearchContactRecord>> searchContacts({
    required LocalSearchNamespace namespace,
    required String query,
    int limit = 20,
  }) async {
    calls.add('contacts');
    return const <LocalChatSearchContactRecord>[
      LocalChatSearchContactRecord(contactId: 'contact-1', displayName: '摄影好友'),
    ];
  }

  @override
  Future<List<ConversationSearchItemView>> searchConversations({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  }) async {
    calls.add('conversations');
    return const <ConversationSearchItemView>[
      ConversationSearchItemView(
        conversationId: 'conversation-1',
        type: 'group',
        title: '摄影讨论群',
        memberCount: 8,
      ),
    ];
  }

  @override
  Future<List<MessageSearchItemView>> searchMessages({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  }) async {
    calls.add('messages');
    return <MessageSearchItemView>[
      MessageSearchItemView(
        messageId: 'message-1',
        conversationId: 'conversation-1',
        conversationTitle: '摄影讨论群',
        messageType: 'text',
        contentPreview: '周末一起拍照',
        timestamp: DateTime.utc(2026, 7, 20),
      ),
    ];
  }
}

final class _SyncSpy implements LocalChatSearchSynchronizer {
  _SyncSpy({this.failure, this.result = true});

  final Object? failure;
  final bool result;
  int calls = 0;

  @override
  Future<bool> sync({bool force = false}) async {
    calls += 1;
    if (failure != null) {
      throw failure!;
    }
    return result;
  }
}

final class _TelemetrySpy implements CacheTelemetrySink {
  final List<String> events = <String>[];

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    events.add(eventName);
  }
}
