import 'dart:async';

import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 两阶段搜索的单一生产仓库：
/// - result：只消费 search-service canonical Remote，禁止本地对象混入最终结果；
/// - suggest：并行合并 canonical Remote 与账号隔离的本地联系人/会话/消息索引。
///
/// 局部依赖失败会产生 typed degrade signal 并写结构化 telemetry，不吞异常、不合成
/// 业务结果。聊天索引同步在后台触发，输入联想永不等待远端同步。
final class HybridSearchRepository implements SearchRepository {
  HybridSearchRepository(
    this._remote,
    this._localChatReader,
    this._localChatSync,
    this._personaContextLoader,
    this._telemetrySink,
  );

  static const _telemetryEvent = 'search_hybrid_degraded';

  final SearchRepository _remote;
  final LocalChatSearchReader _localChatReader;
  final LocalChatSearchSynchronizer _localChatSync;
  final PersonaContextLoader _personaContextLoader;
  final CacheTelemetrySink _telemetrySink;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.mode == SearchMode.result) {
      return _remote.search(
        normalized,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
    }

    unawaited(_syncLocalChatIndex());
    final remoteFuture = _remoteSuggest(
      normalized,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    final localFuture = _localSuggest(normalized);
    final results = await Future.wait<SearchResponse>(<Future<SearchResponse>>[
      remoteFuture,
      localFuture,
    ]);
    return _merge(normalized, results[0], results[1]);
  }

  Future<void> _syncLocalChatIndex() async {
    try {
      await _localChatSync.sync();
    } on Object catch (error) {
      _recordDegrade('local_sync', error);
    }
  }

  Future<SearchResponse> _remoteSuggest(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    try {
      return await _remote.search(
        request,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
    } on Object catch (error) {
      _recordDegrade('remote', error);
      return SearchResponse(
        request: request,
        sections: const <SearchSection>[],
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'search_cloud_suggest_unavailable',
            message: UITextConstants.searchCloudSuggestUnavailable,
          ),
        ],
      );
    }
  }

  Future<SearchResponse> _localSuggest(SearchRequest request) async {
    final degradeSignals = <SearchDegradeSignal>[];
    final sections = <SearchSection>[];
    final namespace = await _resolveNamespace();
    if (namespace == null) {
      return SearchResponse(
        request: request,
        sections: const <SearchSection>[],
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'search_local_namespace_unavailable',
            message: UITextConstants.searchLocalContactsUnavailable,
          ),
        ],
      );
    }

    if (_includes(request, SearchObjectType.chatContact)) {
      try {
        final records = await _localChatReader.searchContacts(
          namespace: namespace,
          query: request.query,
          limit: request.limit,
        );
        final hits = records
            .map((record) {
              final item = record.toSearchItemDto();
              return SearchHit(
                objectType: SearchObjectType.chatContact,
                objectId: item.contactId,
                title: item.displayName,
                subtitle: item.subtitle,
                resolvedFrom: SearchResolvedFrom.local,
                matchedField: item.matchedField,
                payload: SearchHitPayloadChatContact(item),
              );
            })
            .where((hit) => hit.objectId.isNotEmpty && hit.title.isNotEmpty)
            .toList(growable: false);
        if (hits.isNotEmpty) {
          sections.add(
            SearchSection(
              id: 'contacts',
              title:
                  SearchRegistry.sectionById('contacts')?.title ?? 'contacts',
              objectTypes: const <SearchObjectType>[
                SearchObjectType.chatContact,
              ],
              hits: hits,
              resolvedFrom: SearchResolvedFrom.local,
            ),
          );
        }
      } on Object catch (error) {
        _recordDegrade('contacts', error);
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'search_local_contacts_unavailable',
            message: UITextConstants.searchLocalContactsUnavailable,
            objectType: SearchObjectType.chatContact,
          ),
        );
      }
    }

    final includeConversations = _includes(
      request,
      SearchObjectType.chatConversation,
    );
    final includeMessages = _includes(request, SearchObjectType.chatMessage);
    if (includeConversations || includeMessages) {
      try {
        final conversations = includeConversations
            ? await _localChatReader.searchConversations(
                namespace: namespace,
                query: request.query,
                conversationType: request.conversationType,
                limit: request.limit,
              )
            : const <ConversationSearchItemView>[];
        final messages = includeMessages
            ? await _localChatReader.searchMessages(
                namespace: namespace,
                query: request.query,
                conversationType: request.conversationType,
                limit: request.limit,
              )
            : const <MessageSearchItemView>[];
        final hits = <SearchHit>[
          for (final item in conversations)
            SearchHit(
              objectType: SearchObjectType.chatConversation,
              objectId: item.conversationId,
              title: item.title,
              subtitle: item.lastMessagePreview,
              snippet: item.lastMessagePreview,
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: item.matchedField,
              payload: SearchHitPayloadChatConversation(item),
            ),
          for (final item in messages)
            SearchHit(
              objectType: SearchObjectType.chatMessage,
              objectId: item.messageId,
              title: item.conversationTitle?.trim().isNotEmpty == true
                  ? item.conversationTitle!
                  : item.contentPreview,
              subtitle: item.senderDisplayName,
              snippet: item.contentPreview,
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: item.matchedField,
              payload: SearchHitPayloadChatMessage(item),
            ),
        ].take(request.limit).toList(growable: false);
        if (hits.isNotEmpty) {
          sections.add(
            SearchSection(
              id: 'chat_records',
              title:
                  SearchRegistry.sectionById('chat_records')?.title ??
                  'chat_records',
              objectTypes: <SearchObjectType>[
                if (includeConversations) SearchObjectType.chatConversation,
                if (includeMessages) SearchObjectType.chatMessage,
              ],
              hits: hits,
              resolvedFrom: SearchResolvedFrom.local,
            ),
          );
        }
      } on Object catch (error) {
        _recordDegrade('chat_records', error);
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'search_local_messages_unavailable',
            message: UITextConstants.searchLocalMessagesUnavailable,
            objectType: SearchObjectType.chatMessage,
          ),
        );
      }
    }

    return SearchResponse(
      request: request,
      sections: sections,
      degradeSignals: degradeSignals,
    );
  }

  Future<LocalSearchNamespace?> _resolveNamespace() async {
    try {
      final context = await _personaContextLoader();
      return LocalSearchNamespace.fromActivePersonaContext(context);
    } on Object catch (error) {
      _recordDegrade('namespace', error);
      return null;
    }
  }

  bool _includes(SearchRequest request, SearchObjectType type) {
    return request.objectTypes.isEmpty || request.objectTypes.contains(type);
  }

  SearchResponse _merge(
    SearchRequest request,
    SearchResponse remote,
    SearchResponse local,
  ) {
    final sectionByID = <String, SearchSection>{};
    for (final section in <SearchSection>[
      ...local.sections,
      ...remote.sections,
    ]) {
      sectionByID.putIfAbsent(section.id, () => section);
    }
    return SearchResponse(
      request: request,
      sections: sectionByID.values.toList(growable: false),
      degradeSignals: <SearchDegradeSignal>[
        ...local.degradeSignals,
        ...remote.degradeSignals,
      ],
      relatedTerms: remote.relatedTerms,
      searchRequestId: remote.searchRequestId,
    );
  }

  void _recordDegrade(String source, Object error) {
    _telemetrySink.record(_telemetryEvent, <String, Object?>{
      'source': source,
      'errorType': error.runtimeType.toString(),
    });
  }
}
