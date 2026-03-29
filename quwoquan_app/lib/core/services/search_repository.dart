import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';

class SearchRequest {
  const SearchRequest({
    required this.query,
    this.mode = SearchMode.suggest,
    this.objectTypes = const <SearchObjectType>{},
    this.limit = 0,
    this.conversationType,
    this.contentTypes = const <SearchContentTypeFilter>{},
    this.categoryId,
    this.subCategory,
  });

  final String query;
  final SearchMode mode;
  final Set<SearchObjectType> objectTypes;
  final int limit;
  final String? conversationType;
  final Set<SearchContentTypeFilter> contentTypes;
  final String? categoryId;
  final String? subCategory;

  SearchRequest normalized() {
    final trimmedQuery = query.trim();
    final normalizedLimit = limit > 0
        ? limit
        : switch (mode) {
            SearchMode.suggest => SearchContractDefaults.suggestLimit,
            SearchMode.result => SearchContractDefaults.resultLimit,
          };
    return SearchRequest(
      query: trimmedQuery,
      mode: mode,
      objectTypes: objectTypes,
      limit: normalizedLimit.clamp(1, 50).toInt(),
      conversationType: _normalizeConversationType(conversationType),
      contentTypes: contentTypes,
      categoryId: _normalize(categoryId),
      subCategory: _normalize(subCategory),
    );
  }

  Map<String, dynamic> toMap() {
    final normalizedRequest = normalized();
    return <String, dynamic>{
      SearchToolFieldNames.query: normalizedRequest.query,
      SearchToolFieldNames.mode: normalizedRequest.mode.wireValue,
      SearchToolFieldNames.objectTypes: normalizedRequest.objectTypes
          .map((item) => item.wireValue)
          .toList(growable: false),
      SearchToolFieldNames.limit: normalizedRequest.limit,
      if (normalizedRequest.conversationType != null)
        SearchToolFieldNames.conversationType:
            normalizedRequest.conversationType,
      if (normalizedRequest.contentTypes.isNotEmpty)
        SearchToolFieldNames.contentTypes: normalizedRequest.contentTypes
            .map((item) => item.wireValue)
            .toList(growable: false),
      if (normalizedRequest.categoryId != null)
        SearchToolFieldNames.categoryId: normalizedRequest.categoryId,
      if (normalizedRequest.subCategory != null)
        SearchToolFieldNames.subCategory: normalizedRequest.subCategory,
    };
  }
}

class SearchDegradeSignal {
  const SearchDegradeSignal({
    required this.code,
    required this.message,
    this.objectType,
  });

  final String code;
  final String message;
  final SearchObjectType? objectType;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'code': code,
      'message': message,
      if (objectType != null) 'objectType': objectType!.wireValue,
    };
  }
}

class SearchHit {
  const SearchHit({
    required this.objectType,
    required this.objectId,
    required this.title,
    this.subtitle,
    this.snippet,
    required this.resolvedFrom,
    this.matchedField,
    this.payload = const <String, dynamic>{},
  });

  final SearchObjectType objectType;
  final String objectId;
  final String title;
  final String? subtitle;
  final String? snippet;
  final SearchResolvedFrom resolvedFrom;
  final String? matchedField;
  final Map<String, dynamic> payload;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'objectType': objectType.wireValue,
      'objectId': objectId,
      'title': title,
      if (subtitle != null) 'subtitle': subtitle,
      if (snippet != null) 'snippet': snippet,
      'resolvedFrom': resolvedFrom.wireValue,
      if (matchedField != null) 'matchedField': matchedField,
      'payload': payload,
    };
  }
}

class SearchSection {
  const SearchSection({
    required this.id,
    required this.title,
    required this.objectTypes,
    required this.hits,
    required this.resolvedFrom,
    this.degradeSignals = const <SearchDegradeSignal>[],
  });

  final String id;
  final String title;
  final List<SearchObjectType> objectTypes;
  final List<SearchHit> hits;
  final SearchResolvedFrom resolvedFrom;
  final List<SearchDegradeSignal> degradeSignals;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'title': title,
      'objectTypes': objectTypes
          .map((item) => item.wireValue)
          .toList(growable: false),
      'resolvedFrom': resolvedFrom.wireValue,
      'hits': hits.map((item) => item.toMap()).toList(growable: false),
      'degradeSignals': degradeSignals
          .map((item) => item.toMap())
          .toList(growable: false),
    };
  }
}

class SearchResponse {
  const SearchResponse({
    required this.request,
    required this.sections,
    this.degradeSignals = const <SearchDegradeSignal>[],
  });

  final SearchRequest request;
  final List<SearchSection> sections;
  final List<SearchDegradeSignal> degradeSignals;

  List<SearchHit> get hits =>
      sections.expand((section) => section.hits).toList(growable: false);

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'request': request.toMap(),
      'sections': sections.map((item) => item.toMap()).toList(growable: false),
      'hits': hits.map((item) => item.toMap()).toList(growable: false),
      'degradeSignals': degradeSignals
          .map((item) => item.toMap())
          .toList(growable: false),
    };
  }
}

abstract class SearchRepository {
  Future<SearchResponse> search(SearchRequest request);
}

SearchRepository buildAppSearchRepository({
  required CircleRepository circleRepository,
  required ContentRepository contentRepository,
  required HomepageRepository homepageRepository,
  required IntegrationRepository integrationRepository,
  required LocalChatSearchStore localChatSearchStore,
  required LocalChatSearchSyncService localChatSearchSyncService,
  required LocalCircleGroupSnapshotStore localCircleGroupSnapshotStore,
  required PersonaContextLoader personaContextLoader,
}) {
  return AppSearchRepository(
    circleRepository: circleRepository,
    contentRepository: contentRepository,
    homepageRepository: homepageRepository,
    integrationRepository: integrationRepository,
    localChatSearchStore: localChatSearchStore,
    localChatSearchSyncService: localChatSearchSyncService,
    localCircleGroupSnapshotStore: localCircleGroupSnapshotStore,
    personaContextLoader: personaContextLoader,
  );
}

class AppSearchRepository implements SearchRepository {
  AppSearchRepository({
    required CircleRepository circleRepository,
    required ContentRepository contentRepository,
    required HomepageRepository homepageRepository,
    required IntegrationRepository integrationRepository,
    required LocalChatSearchStore localChatSearchStore,
    required LocalChatSearchSyncService localChatSearchSyncService,
    required LocalCircleGroupSnapshotStore localCircleGroupSnapshotStore,
    required PersonaContextLoader personaContextLoader,
  }) : _circleRepository = circleRepository,
       _contentRepository = contentRepository,
       _homepageRepository = homepageRepository,
       _integrationRepository = integrationRepository,
       _localChatSearchStore = localChatSearchStore,
       _localChatSearchSyncService = localChatSearchSyncService,
       _localCircleGroupSnapshotStore = localCircleGroupSnapshotStore,
       _personaContextLoader = personaContextLoader;

  final CircleRepository _circleRepository;
  final ContentRepository _contentRepository;
  final HomepageRepository _homepageRepository;
  final IntegrationRepository _integrationRepository;
  final LocalChatSearchStore _localChatSearchStore;
  final LocalChatSearchSyncService _localChatSearchSyncService;
  final LocalCircleGroupSnapshotStore _localCircleGroupSnapshotStore;
  final PersonaContextLoader _personaContextLoader;

  @override
  Future<SearchResponse> search(SearchRequest request) async {
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }
    try {
      final effectiveObjectTypes = _effectiveObjectTypes(normalized);
      final sections = <SearchSection>[];
      final degradeSignals = <SearchDegradeSignal>[];
      final needsLocalNamespace = effectiveObjectTypes.any((type) {
        return type == SearchObjectType.chatContact ||
            type == SearchObjectType.chatConversation ||
            type == SearchObjectType.chatMessage ||
            type == SearchObjectType.circleGroup;
      });
      final localNamespace = needsLocalNamespace
          ? await _resolveLocalNamespace()
          : null;

      if (localNamespace != null &&
          effectiveObjectTypes.any((type) {
            return type == SearchObjectType.chatContact ||
                type == SearchObjectType.chatConversation ||
                type == SearchObjectType.chatMessage;
          })) {
        await _localChatSearchSyncService.sync(force: false);
      }
      if (localNamespace != null &&
          effectiveObjectTypes.contains(SearchObjectType.circleGroup)) {
        final seeded = await _localCircleGroupSnapshotStore.ensureSeeded(
          namespace: localNamespace,
          circleRepository: _circleRepository,
        );
        if (!seeded) {
          degradeSignals.add(
            const SearchDegradeSignal(
              code: 'circle_group_snapshot_seed_failed',
              message: 'circle.group 本地快照预热失败，当前仅保留远端与已有本地结果。',
              objectType: SearchObjectType.circleGroup,
            ),
          );
        }
      }

      if (normalized.mode == SearchMode.suggest) {
        final suggestResults = await Future.wait<_SectionBuildResult?>(
          <Future<_SectionBuildResult?>>[
            if (effectiveObjectTypes.contains(SearchObjectType.chatContact))
              _buildContactsSection(normalized, namespace: localNamespace),
            if (effectiveObjectTypes.contains(
                  SearchObjectType.chatConversation,
                ) ||
                effectiveObjectTypes.contains(SearchObjectType.chatMessage))
              _buildChatRecordsSection(normalized, namespace: localNamespace),
            if (effectiveObjectTypes.contains(SearchObjectType.circleGroup) ||
                effectiveObjectTypes.contains(SearchObjectType.circleCircle))
              _buildGroupsSection(
                normalized,
                namespace: localNamespace,
                objectTypes: effectiveObjectTypes,
              ),
          ],
        );
        for (final result in suggestResults) {
          if (result == null) {
            continue;
          }
          degradeSignals.addAll(result.degradeSignals);
          if (result.section.hits.isEmpty) {
            continue;
          }
          sections.add(result.section);
        }
      } else {
        final resultSections = await Future.wait<_SectionBuildResult?>(
          <Future<_SectionBuildResult?>>[
            if (effectiveObjectTypes.contains(SearchObjectType.contentPost))
              _buildContentSection(normalized),
            if (effectiveObjectTypes.contains(SearchObjectType.entityHomepage))
              _buildHomepageSection(normalized),
            if (effectiveObjectTypes.contains(SearchObjectType.circleGroup) ||
                effectiveObjectTypes.contains(SearchObjectType.circleCircle))
              _buildGroupsSection(
                normalized,
                namespace: localNamespace,
                objectTypes: effectiveObjectTypes,
              ),
            if (effectiveObjectTypes.contains(
              SearchObjectType.integrationLocationPoi,
            ))
              _buildLocationSection(normalized),
          ],
        );
        for (final result in resultSections) {
          if (result == null) {
            continue;
          }
          degradeSignals.addAll(result.degradeSignals);
          if (result.section.hits.isEmpty) {
            continue;
          }
          sections.add(result.section);
        }
        if (effectiveObjectTypes.contains(SearchObjectType.webDocument)) {
          degradeSignals.add(
            const SearchDegradeSignal(
              code: 'web_document_requires_tool',
              message:
                  'web.document 由 assistant search tool 承接，App facade 不直接执行网页检索。',
              objectType: SearchObjectType.webDocument,
            ),
          );
        }
      }

      return SearchResponse(
        request: normalized,
        sections: sections,
        degradeSignals: degradeSignals,
      );
    } catch (_) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'search_repository_failed',
            message: '统一检索当前已 fail-closed 返回空结果，请稍后重试。',
          ),
        ],
      );
    }
  }

  Set<SearchObjectType> _effectiveObjectTypes(SearchRequest request) {
    if (request.objectTypes.isNotEmpty) {
      return request.objectTypes;
    }
    return switch (request.mode) {
      SearchMode.suggest => <SearchObjectType>{
        SearchObjectType.chatContact,
        SearchObjectType.chatConversation,
        SearchObjectType.chatMessage,
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
      },
      SearchMode.result => <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.circleCircle,
        SearchObjectType.entityHomepage,
        SearchObjectType.circleGroup,
        SearchObjectType.integrationLocationPoi,
      },
    };
  }

  Future<_SectionBuildResult?> _buildContactsSection(
    SearchRequest request, {
    required LocalSearchNamespace? namespace,
  }) async {
    if (namespace == null) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'contacts',
          title: _sectionTitle('contacts', '联系人'),
          objectTypes: const <SearchObjectType>[SearchObjectType.chatContact],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'chat_local_namespace_unavailable',
            message: '当前无法确认本地账号命名空间，联系人搜索已 fail-closed。',
            objectType: SearchObjectType.chatContact,
          ),
        ],
      );
    }
    try {
      final contacts = await _localChatSearchStore.searchContacts(
        namespace: namespace,
        query: request.query,
        limit: request.limit,
      );
      final conversations = await _localChatSearchStore.listConversationViews(
        namespace: namespace,
        limit: 200,
      );
      final hits = contacts
          .map((contact) {
            final userId = (contact['contactId'] ?? contact['userId'] ?? '')
                .toString()
                .trim();
            final displayName =
                (contact['displayName'] ?? contact['nickname'] ?? userId)
                    .toString()
                    .trim();
            final conversationId = _firstNonEmpty(<Object?>[
              contact['conversationId'],
              _resolveContactConversationId(
                displayName: displayName,
                allConversations: conversations,
              ),
            ]);
            final payload = <String, dynamic>{
              ...contact,
              'contactId': userId,
              'displayName': displayName,
              if (conversationId.isNotEmpty) 'conversationId': conversationId,
            };
            return SearchHit(
              objectType: SearchObjectType.chatContact,
              objectId: userId,
              title: displayName,
              subtitle: payload['subtitle']?.toString() ?? '联系人',
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: payload['matchedField']?.toString(),
              payload: payload,
            );
          })
          .where((item) => item.objectId.isNotEmpty && item.title.isNotEmpty)
          .toList(growable: false);
      return _SectionBuildResult(
        section: SearchSection(
          id: 'contacts',
          title: _sectionTitle('contacts', '联系人'),
          objectTypes: const <SearchObjectType>[SearchObjectType.chatContact],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: hits.isEmpty
            ? const <SearchDegradeSignal>[
                SearchDegradeSignal(
                  code: 'chat_local_contact_miss',
                  message: '本地联系人索引未命中当前关键词。',
                  objectType: SearchObjectType.chatContact,
                ),
              ]
            : const <SearchDegradeSignal>[],
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'contacts',
          title: _sectionTitle('contacts', '联系人'),
          objectTypes: const <SearchObjectType>[SearchObjectType.chatContact],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'chat_local_contact_failed',
            message: '本地联系人索引读取失败，当前已 fail-closed。',
            objectType: SearchObjectType.chatContact,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildChatRecordsSection(
    SearchRequest request, {
    required LocalSearchNamespace? namespace,
  }) async {
    if (namespace == null) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'chat_records',
          title: _sectionTitle('chat_records', '聊天记录'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.chatConversation,
            SearchObjectType.chatMessage,
          ],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'chat_local_namespace_unavailable',
            message: '当前无法确认本地账号命名空间，聊天记录搜索已 fail-closed。',
            objectType: SearchObjectType.chatConversation,
          ),
        ],
      );
    }
    try {
      final conversationHits = <SearchHit>[];
      final messageHits = <SearchHit>[];
      if (request.objectTypes.isEmpty ||
          request.objectTypes.contains(SearchObjectType.chatConversation)) {
        final conversations = await _localChatSearchStore.searchConversations(
          namespace: namespace,
          query: request.query,
          conversationType: request.conversationType,
          limit: request.limit,
        );
        conversationHits.addAll(
          conversations.map(
            (conversation) => SearchHit(
              objectType: SearchObjectType.chatConversation,
              objectId: conversation.conversationId,
              title: conversation.title,
              subtitle: conversation.lastMessagePreview,
              snippet: conversation.lastMessagePreview,
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: conversation.matchedField,
              payload: _conversationSearchItemToMap(conversation),
            ),
          ),
        );
      }
      if (request.objectTypes.isEmpty ||
          request.objectTypes.contains(SearchObjectType.chatMessage)) {
        final messages = await _localChatSearchStore.searchMessages(
          namespace: namespace,
          query: request.query,
          conversationType: request.conversationType,
          limit: request.limit,
        );
        messageHits.addAll(
          messages.map(
            (message) => SearchHit(
              objectType: SearchObjectType.chatMessage,
              objectId: message.messageId,
              title: message.conversationTitle ?? message.contentPreview,
              subtitle: (message.senderDisplayName ?? '').isNotEmpty
                  ? message.senderDisplayName
                  : message.conversationTitle ?? message.contentPreview,
              snippet: message.contentPreview,
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: message.matchedField,
              payload: _messageSearchItemToMap(message),
            ),
          ),
        );
      }
      final hits = <SearchHit>[
        ...conversationHits.take(request.limit),
        ...messageHits.take(request.limit),
      ];
      return _SectionBuildResult(
        section: SearchSection(
          id: 'chat_records',
          title: _sectionTitle('chat_records', '聊天记录'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.chatConversation,
            SearchObjectType.chatMessage,
          ],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: hits.isEmpty
            ? const <SearchDegradeSignal>[
                SearchDegradeSignal(
                  code: 'chat_local_record_miss',
                  message: '本地聊天记录索引未命中当前关键词。',
                  objectType: SearchObjectType.chatMessage,
                ),
              ]
            : const <SearchDegradeSignal>[],
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'chat_records',
          title: _sectionTitle('chat_records', '聊天记录'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.chatConversation,
            SearchObjectType.chatMessage,
          ],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'chat_local_record_failed',
            message: '本地聊天记录索引读取失败，当前已 fail-closed。',
            objectType: SearchObjectType.chatMessage,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildGroupsSection(
    SearchRequest request, {
    required LocalSearchNamespace? namespace,
    required Set<SearchObjectType> objectTypes,
  }) async {
    final degradeSignals = <SearchDegradeSignal>[];
    final includeCircleGroups = objectTypes.contains(
      SearchObjectType.circleGroup,
    );
    final includeCircles = objectTypes.contains(SearchObjectType.circleCircle);
    final hits = <SearchHit>[];

    if (includeCircleGroups) {
      SearchResolvedFrom groupResolvedFrom = SearchResolvedFrom.remote;
      List<Map<String, dynamic>> remoteGroups = const <Map<String, dynamic>>[];
      var remoteSearchFailed = false;
      try {
        remoteGroups = await _searchRemoteCircleGroups(request);
      } catch (_) {
        remoteSearchFailed = true;
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'circle_group_remote_failed',
            message: 'circle.group 远端检索失败，准备回退本地快照。',
            objectType: SearchObjectType.circleGroup,
          ),
        );
      }
      if (remoteGroups.isNotEmpty && namespace != null) {
        try {
          await _localCircleGroupSnapshotStore.upsertGroups(
            namespace: namespace,
            groups: remoteGroups,
          );
        } catch (_) {
          degradeSignals.add(
            const SearchDegradeSignal(
              code: 'circle_group_snapshot_update_failed',
              message: 'circle.group 本地快照更新失败，当前仅返回远端结果。',
              objectType: SearchObjectType.circleGroup,
            ),
          );
        }
      }
      if (!remoteSearchFailed && remoteGroups.isEmpty) {
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'circle_group_remote_empty',
            message: 'circle.group 远端返回空结果，准备回退本地快照。',
            objectType: SearchObjectType.circleGroup,
          ),
        );
      }

      var groupPayloads = remoteGroups;
      if (groupPayloads.isEmpty) {
        if (namespace == null) {
          degradeSignals.add(
            const SearchDegradeSignal(
              code: 'circle_group_local_namespace_unavailable',
              message: '当前无法确认本地账号命名空间，circle.group 无法执行本地回退。',
              objectType: SearchObjectType.circleGroup,
            ),
          );
        } else {
          try {
            groupPayloads = await _localCircleGroupSnapshotStore.searchGroups(
              namespace: namespace,
              query: request.query,
              limit: request.limit,
            );
            if (groupPayloads.isNotEmpty) {
              groupResolvedFrom = SearchResolvedFrom.localFallback;
            } else {
              degradeSignals.add(
                const SearchDegradeSignal(
                  code: 'circle_group_local_miss',
                  message: 'circle.group 本地快照未命中当前关键词。',
                  objectType: SearchObjectType.circleGroup,
                ),
              );
            }
          } catch (_) {
            degradeSignals.add(
              const SearchDegradeSignal(
                code: 'circle_group_local_failed',
                message: 'circle.group 本地快照检索失败，当前已 fail-closed。',
                objectType: SearchObjectType.circleGroup,
              ),
            );
          }
        }
      }

      hits.addAll(
        groupPayloads
            .take(request.limit)
            .map(
              (payload) =>
                  _circleGroupHit(payload, groupResolvedFrom, request.query),
            )
            .where((item) => item.objectId.isNotEmpty && item.title.isNotEmpty),
      );
    }

    if (includeCircles) {
      try {
        final circles = await _searchRemoteCircles(request);
        hits.addAll(
          circles
              .take(request.limit)
              .map((item) => _circleHit(item, SearchResolvedFrom.remote))
              .where(
                (item) => item.objectId.isNotEmpty && item.title.isNotEmpty,
              ),
        );
      } catch (_) {
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'circle_remote_failed',
            message: 'circle.circle 远端检索失败，当前已 fail-closed。',
            objectType: SearchObjectType.circleCircle,
          ),
        );
      }
    }

    final dedupedHits = <String, SearchHit>{};
    for (final hit in hits) {
      dedupedHits.putIfAbsent(
        '${hit.objectType.wireValue}:${hit.objectId}',
        () => hit,
      );
    }
    final limitedHits = dedupedHits.values
        .take(request.limit)
        .toList(growable: false);
    final resolvedFrom =
        limitedHits.any(
          (item) => item.resolvedFrom == SearchResolvedFrom.localFallback,
        )
        ? SearchResolvedFrom.localFallback
        : SearchResolvedFrom.remote;
    return _SectionBuildResult(
      section: SearchSection(
        id: 'groups',
        title: _sectionTitle('groups', '群组'),
        objectTypes: <SearchObjectType>[
          if (includeCircleGroups) SearchObjectType.circleGroup,
          if (includeCircles) SearchObjectType.circleCircle,
        ],
        hits: limitedHits,
        resolvedFrom: resolvedFrom,
        degradeSignals: degradeSignals,
      ),
      degradeSignals: degradeSignals,
    );
  }

  Future<_SectionBuildResult?> _buildContentSection(
    SearchRequest request,
  ) async {
    try {
      final hits = <SearchHit>[];
      if (request.contentTypes.isEmpty) {
        final items = await _contentRepository.searchPosts(
          query: request.query,
          categoryId: request.categoryId,
          limit: request.limit,
        );
        hits.addAll(
          items.map((item) => _postHit(item, SearchResolvedFrom.remote)),
        );
      } else {
        final merged = <String, PostSearchItemView>{};
        for (final type in request.contentTypes) {
          final items = await _contentRepository.searchPosts(
            query: request.query,
            identity: type.identity,
            type: type.contentType,
            categoryId: request.categoryId,
            limit: request.limit,
          );
          for (final item in items) {
            merged.putIfAbsent(item.postId, () => item);
          }
        }
        hits.addAll(
          merged.values.map(
            (item) => _postHit(item, SearchResolvedFrom.remote),
          ),
        );
      }
      if (hits.isEmpty) {
        return null;
      }
      return _SectionBuildResult(
        section: SearchSection(
          id: 'content',
          title: _sectionTitle('content', '内容'),
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: hits.take(request.limit).toList(growable: false),
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'content',
          title: _sectionTitle('content', '内容'),
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'content_remote_failed',
            message: '内容搜索远端请求失败，当前已 fail-closed。',
            objectType: SearchObjectType.contentPost,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildHomepageSection(
    SearchRequest request,
  ) async {
    try {
      final items = await _homepageRepository.searchHomepages(
        query: request.query,
        limit: request.limit,
      );
      final hits = items
          .map(
            (item) => SearchHit(
              objectType: SearchObjectType.entityHomepage,
              objectId: item.id,
              title: item.title,
              subtitle: item.subtitle,
              snippet: item.address,
              resolvedFrom: SearchResolvedFrom.remote,
              matchedField: 'title',
              payload: item.toMap(),
            ),
          )
          .where((item) => item.objectId.isNotEmpty && item.title.isNotEmpty)
          .toList(growable: false);
      if (hits.isEmpty) {
        return null;
      }
      return _SectionBuildResult(
        section: SearchSection(
          id: 'homepages',
          title: _sectionTitle('homepages', '主页'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.entityHomepage,
          ],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'homepages',
          title: _sectionTitle('homepages', '主页'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.entityHomepage,
          ],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'homepage_remote_failed',
            message: '主页搜索远端请求失败，当前已 fail-closed。',
            objectType: SearchObjectType.entityHomepage,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildLocationSection(
    SearchRequest request,
  ) async {
    try {
      final items = await _integrationRepository.searchLocations(
        query: request.query,
        limit: request.limit,
      );
      final hits = items
          .map(
            (item) => _locationHit(
              item,
              SearchResolvedFrom.remote,
              query: request.query,
            ),
          )
          .where((item) => item.objectId.isNotEmpty && item.title.isNotEmpty)
          .toList(growable: false);
      if (hits.isEmpty) {
        return null;
      }
      return _SectionBuildResult(
        section: SearchSection(
          id: 'locations',
          title: _sectionTitle('locations', '位置'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.integrationLocationPoi,
          ],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'locations',
          title: _sectionTitle('locations', '位置'),
          objectTypes: const <SearchObjectType>[
            SearchObjectType.integrationLocationPoi,
          ],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'location_remote_failed',
            message: '位置搜索远端请求失败，当前已 fail-closed。',
            objectType: SearchObjectType.integrationLocationPoi,
          ),
        ],
      );
    }
  }

  String _resolveContactConversationId({
    required String displayName,
    required List<ConversationSearchItemView> allConversations,
  }) {
    final normalizedName = displayName.trim().toLowerCase();
    for (final conversation in allConversations) {
      final normalizedTitle = conversation.title.trim().toLowerCase();
      final isDirectLike =
          conversation.type == 'direct' || conversation.type == 'encrypted';
      if (!isDirectLike) {
        continue;
      }
      if (normalizedTitle == normalizedName ||
          normalizedTitle.contains(normalizedName) ||
          normalizedName.contains(normalizedTitle)) {
        return conversation.conversationId;
      }
    }
    for (final conversation in allConversations) {
      final isDirectLike =
          conversation.type == 'direct' || conversation.type == 'encrypted';
      if (isDirectLike) {
        return conversation.conversationId;
      }
    }
    return allConversations.isNotEmpty
        ? allConversations.first.conversationId
        : '';
  }

  Future<LocalSearchNamespace?> _resolveLocalNamespace() async {
    try {
      final context = await _personaContextLoader();
      return LocalSearchNamespace.fromActivePersonaContext(context);
    } catch (_) {
      return null;
    }
  }

  Future<List<Map<String, dynamic>>> _searchRemoteCircleGroups(
    SearchRequest request,
  ) async {
    final candidateCircles = await _circleRepository.listCircles(limit: 12);
    final merged = <String, Map<String, dynamic>>{};
    for (final circle in candidateCircles) {
      final circleId = _firstNonEmpty(<Object?>[circle['id'], circle['_id']]);
      if (circleId.isEmpty) {
        continue;
      }
      final circleName = _firstNonEmpty(<Object?>[circle['name']]);
      List<Map<String, dynamic>> groups;
      try {
        groups = await _circleRepository.searchCircleGroups(
          circleId,
          query: request.query,
          limit: request.limit,
        );
      } catch (_) {
        continue;
      }
      for (final raw in groups) {
        final payload = _normalizeCircleGroupPayload(<String, dynamic>{
          ...raw,
          'circleId': circleId,
          if (circleName.isNotEmpty) 'circleName': circleName,
        });
        final groupId = _firstNonEmpty(<Object?>[
          payload['groupId'],
          payload['circleGroupId'],
        ]);
        if (groupId.isEmpty) {
          continue;
        }
        merged.putIfAbsent('$circleId::$groupId', () => payload);
        if (merged.length >= request.limit) {
          return merged.values.toList(growable: false);
        }
      }
    }
    return merged.values.toList(growable: false);
  }

  Future<List<CircleSearchItemView>> _searchRemoteCircles(
    SearchRequest request,
  ) async {
    final result = await _circleRepository.searchCircles(
      query: request.query,
      categoryId: request.categoryId,
      subCategory: request.subCategory,
      limit: request.limit,
    );
    return result.items;
  }

  SearchHit _circleGroupHit(
    Map<String, dynamic> payload,
    SearchResolvedFrom resolvedFrom,
    String query,
  ) {
    final normalizedPayload = _normalizeCircleGroupPayload(payload);
    return SearchHit(
      objectType: SearchObjectType.circleGroup,
      objectId: _firstNonEmpty(<Object?>[
        normalizedPayload['groupId'],
        normalizedPayload['circleId'],
      ]),
      title: _firstNonEmpty(<Object?>[
        normalizedPayload['name'],
        normalizedPayload['title'],
      ]),
      subtitle: _firstNonEmpty(<Object?>[
        normalizedPayload['description'],
        normalizedPayload['circleName'],
      ]),
      snippet: _string(normalizedPayload['description']),
      resolvedFrom: resolvedFrom,
      matchedField: _matchedFieldForCircleGroup(
        query: query,
        payload: normalizedPayload,
      ),
      payload: normalizedPayload,
    );
  }

  SearchHit _circleHit(
    CircleSearchItemView item,
    SearchResolvedFrom resolvedFrom,
  ) {
    return SearchHit(
      objectType: SearchObjectType.circleCircle,
      objectId: item.circleId,
      title: item.name,
      subtitle: _firstNonEmpty(<Object?>[item.subCategory, item.description]),
      snippet: item.description,
      resolvedFrom: resolvedFrom,
      matchedField: item.matchedField,
      payload: <String, dynamic>{
        'id': item.circleId,
        'circleId': item.circleId,
        'name': item.name,
        'description': item.description,
        'coverUrl': item.coverUrl,
        'categoryId': item.categoryId,
        'subCategory': item.subCategory,
        'domainId': item.domainId,
        'kind': item.kind,
        'displaySubjectType': item.displaySubjectType,
        'memberCount': item.memberCount,
        'postCount': item.postCount,
        'highlightText': item.highlightText,
        'matchedField': item.matchedField,
      },
    );
  }

  SearchHit _locationHit(
    LocationPoiDto item,
    SearchResolvedFrom resolvedFrom, {
    required String query,
  }) {
    return SearchHit(
      objectType: SearchObjectType.integrationLocationPoi,
      objectId: item.id,
      title: item.name,
      subtitle: _string(item.address),
      snippet: _string(item.address),
      resolvedFrom: resolvedFrom,
      matchedField: _matchesText(query, <Object?>[item.address])
          ? 'address'
          : 'name',
      payload: item.toMap(),
    );
  }

  Map<String, dynamic> _normalizeCircleGroupPayload(Map<String, dynamic> raw) {
    final circleId = _firstNonEmpty(<Object?>[
      raw['circleId'],
      raw['circle_id'],
    ]);
    final groupId = _firstNonEmpty(<Object?>[
      raw['groupId'],
      raw['circleGroupId'],
      raw['group_id'],
      raw['id'],
      raw['_id'],
    ]);
    final name = _firstNonEmpty(<Object?>[
      raw['name'],
      raw['title'],
      raw['highlightText'],
      groupId,
    ]);
    final description = _firstNonEmpty(<Object?>[
      raw['description'],
      raw['summary'],
    ]);
    final payload = <String, dynamic>{
      ...raw,
      'circleId': circleId,
      'groupId': groupId,
      'name': name,
      'description': description,
      'circleName': _firstNonEmpty(<Object?>[
        raw['circleName'],
        raw['circle_name'],
      ]),
      'memberCount': raw['memberCount'],
      'matchedField': raw['matchedField'],
      'highlightText': raw['highlightText'] ?? name,
    };
    return payload;
  }

  String _matchedFieldForCircleGroup({
    required String query,
    required Map<String, dynamic> payload,
  }) {
    if (_matchesText(query, <Object?>[payload['description']])) {
      return 'description';
    }
    if (_matchesText(query, <Object?>[payload['circleName']])) {
      return 'circleName';
    }
    return 'name';
  }

  String _sectionTitle(String id, String fallback) {
    return SearchRegistry.sectionById(id)?.title ?? fallback;
  }

  bool _matchesText(String query, List<Object?> values) {
    final normalizedQuery = _normalize(query) ?? '';
    if (normalizedQuery.isEmpty) {
      return false;
    }
    for (final value in values) {
      final normalizedValue = _normalize(value?.toString());
      if (normalizedValue != null &&
          normalizedValue.contains(normalizedQuery)) {
        return true;
      }
    }
    return false;
  }

  SearchHit _postHit(PostSearchItemView item, SearchResolvedFrom resolvedFrom) {
    return SearchHit(
      objectType: SearchObjectType.contentPost,
      objectId: item.postId,
      title: item.title?.trim().isNotEmpty == true
          ? item.title!.trim()
          : (item.summary?.trim().isNotEmpty == true
                ? item.summary!.trim()
                : item.postId),
      subtitle: item.circleName ?? item.authorDisplayName,
      snippet: item.summary,
      resolvedFrom: resolvedFrom,
      matchedField: item.matchedField,
      payload: <String, dynamic>{
        'postId': item.postId,
        'contentType': item.contentType,
        'contentIdentity': item.contentIdentity,
        'title': item.title,
        'summary': item.summary,
        'coverUrl': item.coverUrl,
        'authorProfileSubjectId': item.authorProfileSubjectId,
        'authorDisplayName': item.authorDisplayName,
        'authorAvatarUrl': item.authorAvatarUrl,
        'circleId': item.circleId,
        'circleName': item.circleName,
        'categoryId': item.categoryId,
        'subCategory': item.subCategory,
        'likeCount': item.likeCount,
        'highlightText': item.highlightText,
        'matchedField': item.matchedField,
        'publishedAt': item.publishedAt?.toIso8601String(),
      },
    );
  }

  Map<String, dynamic> _conversationSearchItemToMap(
    ConversationSearchItemView conversation,
  ) {
    return <String, dynamic>{
      'conversationId': conversation.conversationId,
      'type': conversation.type,
      'title': conversation.title,
      'avatarUrl': conversation.avatarUrl,
      'avatarCompositeUrls': conversation.avatarCompositeUrls,
      'lastMessagePreview': conversation.lastMessagePreview,
      'lastMessageTime': conversation.lastMessageTime?.toIso8601String(),
      'memberCount': conversation.memberCount,
      'circleId': conversation.circleId,
      'circleGroupId': conversation.circleGroupId,
      'highlightText': conversation.highlightText,
      'matchedField': conversation.matchedField,
    };
  }

  Map<String, dynamic> _messageSearchItemToMap(MessageSearchItemView message) {
    return <String, dynamic>{
      'messageId': message.messageId,
      'conversationId': message.conversationId,
      'conversationTitle': message.conversationTitle,
      'conversationAvatarUrl': message.conversationAvatarUrl,
      'senderProfileSubjectId': message.senderProfileSubjectId,
      'senderDisplayName': message.senderDisplayName,
      'senderAvatarUrl': message.senderAvatarUrl,
      'messageType': message.messageType,
      'contentPreview': message.contentPreview,
      'seq': message.seq,
      'timestamp': message.timestamp.toIso8601String(),
      'highlightText': message.highlightText,
      'matchedField': message.matchedField,
    };
  }

  String _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = _string(value);
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  String _string(Object? value) {
    return value?.toString().trim() ?? '';
  }
}

class _SectionBuildResult {
  const _SectionBuildResult({
    required this.section,
    this.degradeSignals = const <SearchDegradeSignal>[],
  });

  final SearchSection section;
  final List<SearchDegradeSignal> degradeSignals;
}

String? _normalize(String? value) {
  final normalized = value?.trim().toLowerCase();
  if (normalized == null || normalized.isEmpty) {
    return null;
  }
  return normalized;
}

String? _normalizeConversationType(String? value) {
  final normalized = _normalize(value);
  if (normalized == null) {
    return null;
  }
  return SearchConversationType.fromWire(normalized)?.wireValue;
}
