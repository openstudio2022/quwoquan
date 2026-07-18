import 'dart:async';

import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'search_repository_models.dart';

abstract class SearchRepository {
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

SearchRepository buildAppSearchRepository({
  required CircleRepository circleRepository,
  required CircleGroupQueryReader circleGroupQuery,
  required ContentPostSearchRepository contentPostSearchRepository,
  required HomepageRepository homepageRepository,
  required LocationSearchReader locationSearchReader,
  required UserProfileRepository userProfileRepository,
  required LocalChatSearchStore localChatSearchStore,
  required LocalChatSearchSyncService localChatSearchSyncService,
  required LocalCircleGroupSnapshotStore localCircleGroupSnapshotStore,
  required PersonaContextLoader personaContextLoader,
}) {
  return AppSearchRepository(
    circleRepository: circleRepository,
    circleGroupQuery: circleGroupQuery,
    contentPostSearchRepository: contentPostSearchRepository,
    homepageRepository: homepageRepository,
    locationSearchReader: locationSearchReader,
    userProfileRepository: userProfileRepository,
    localChatSearchStore: localChatSearchStore,
    localChatSearchSyncService: localChatSearchSyncService,
    localCircleGroupSnapshotStore: localCircleGroupSnapshotStore,
    personaContextLoader: personaContextLoader,
  );
}

class AppSearchRepository implements SearchRepository {
  AppSearchRepository({
    required this._circleRepository,
    required this._circleGroupQuery,
    required this._contentPostSearchRepository,
    required this._homepageRepository,
    required this._locationSearchReader,
    required this._userProfileRepository,
    required this._localChatSearchStore,
    required this._localChatSearchSyncService,
    required this._localCircleGroupSnapshotStore,
    required this._personaContextLoader,
  });

  final CircleRepository _circleRepository;
  final CircleGroupQueryReader _circleGroupQuery;
  final ContentPostSearchRepository _contentPostSearchRepository;
  final HomepageRepository _homepageRepository;
  final LocationSearchReader _locationSearchReader;
  final UserProfileRepository _userProfileRepository;
  final LocalChatSearchStore _localChatSearchStore;
  final LocalChatSearchSyncService _localChatSearchSyncService;
  final LocalCircleGroupSnapshotStore _localCircleGroupSnapshotStore;
  final PersonaContextLoader _personaContextLoader;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    cancellation?.throwIfCancelled();
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      cancellation?.throwIfCancelled();
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

      if (normalized.mode == SearchMode.suggest &&
          localNamespace != null &&
          effectiveObjectTypes.any((type) {
            return type == SearchObjectType.chatContact ||
                type == SearchObjectType.chatConversation ||
                type == SearchObjectType.chatMessage;
          })) {
        unawaited(
          _localChatSearchSyncService
              .sync(force: false)
              .then<void>((_) {}, onError: (_, _) {}),
        );
      }
      if (normalized.mode == SearchMode.suggest &&
          localNamespace != null &&
          effectiveObjectTypes.contains(SearchObjectType.circleGroup)) {
        unawaited(
          _localCircleGroupSnapshotStore
              .ensureSeeded(
                namespace: localNamespace,
                circleRepository: _circleRepository,
                circleGroupQuery: _circleGroupQuery,
              )
              .then<void>((_) {}, onError: (_, _) {}),
        );
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
            if (effectiveObjectTypes.contains(SearchObjectType.userProfile))
              _buildUserProfileSection(normalized),
            if (effectiveObjectTypes.contains(SearchObjectType.locationPlace))
              _buildPlaceSection(normalized),
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

      cancellation?.throwIfCancelled();
      return SearchResponse(
        request: normalized,
        sections: sections,
        degradeSignals: degradeSignals,
      );
    } on CloudOperationCancelledException {
      rethrow;
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
        SearchObjectType.integrationLocationPoi,
        SearchObjectType.userProfile,
      },
      SearchMode.result => <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.circleCircle,
        SearchObjectType.entityHomepage,
        SearchObjectType.circleGroup,
        SearchObjectType.userProfile,
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
      final contactsFuture = _localChatSearchStore.searchContacts(
        namespace: namespace,
        query: request.query,
        limit: request.limit,
      );
      final conversationsFuture = _localChatSearchStore.listConversationViews(
        namespace: namespace,
        limit: 200,
      );
      final contacts = await contactsFuture;
      final conversations = await conversationsFuture;
      final hits = contacts
          .map((contact) {
            final userId = contact.contactId.trim();
            final displayName = contact.displayName.trim();
            final conversationId = _firstNonEmpty(<Object?>[
              contact.conversationId,
              _resolveContactConversationId(
                displayName: displayName,
                allConversations: conversations,
              ),
            ]);
            final payload = contact.toSearchItemDto().copyWith(
              contactId: userId,
              displayName: displayName,
              conversationId: conversationId.isNotEmpty ? conversationId : null,
            );
            return SearchHit(
              objectType: SearchObjectType.chatContact,
              objectId: userId,
              title: displayName,
              subtitle: payload.subtitle ?? '联系人',
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: payload.matchedField,
              payload: SearchHitPayloadChatContact(payload),
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
      final conversationHitsFuture =
          request.objectTypes.isEmpty ||
              request.objectTypes.contains(SearchObjectType.chatConversation)
          ? _localChatSearchStore
                .searchConversations(
                  namespace: namespace,
                  query: request.query,
                  conversationType: request.conversationType,
                  limit: request.limit,
                )
                .then(
                  (conversations) => conversations
                      .map(
                        (conversation) => SearchHit(
                          objectType: SearchObjectType.chatConversation,
                          objectId: conversation.conversationId,
                          title: conversation.title,
                          subtitle: conversation.lastMessagePreview,
                          snippet: conversation.lastMessagePreview,
                          resolvedFrom: SearchResolvedFrom.local,
                          matchedField: conversation.matchedField,
                          payload: SearchHitPayloadWireMap(
                            _conversationSearchItemToMap(conversation),
                          ),
                        ),
                      )
                      .toList(growable: false),
                )
          : Future<List<SearchHit>>.value(const <SearchHit>[]);
      final messageHitsFuture =
          request.objectTypes.isEmpty ||
              request.objectTypes.contains(SearchObjectType.chatMessage)
          ? _localChatSearchStore
                .searchMessages(
                  namespace: namespace,
                  query: request.query,
                  conversationType: request.conversationType,
                  limit: request.limit,
                )
                .then(
                  (messages) => messages
                      .map(
                        (message) => SearchHit(
                          objectType: SearchObjectType.chatMessage,
                          objectId: message.messageId,
                          title:
                              message.conversationTitle ??
                              message.contentPreview,
                          subtitle: (message.senderDisplayName ?? '').isNotEmpty
                              ? message.senderDisplayName
                              : message.conversationTitle ??
                                    message.contentPreview,
                          snippet: message.contentPreview,
                          resolvedFrom: SearchResolvedFrom.local,
                          matchedField: message.matchedField,
                          payload: SearchHitPayloadWireMap(
                            _messageSearchItemToMap(message),
                          ),
                        ),
                      )
                      .toList(growable: false),
                )
          : Future<List<SearchHit>>.value(const <SearchHit>[]);
      final localHits = await Future.wait<List<SearchHit>>(
        <Future<List<SearchHit>>>[conversationHitsFuture, messageHitsFuture],
      );
      final conversationHits = localHits[0];
      final messageHits = localHits[1];
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
    if (request.mode == SearchMode.suggest) {
      return _buildSuggestedGroupsSection(
        request,
        namespace: namespace,
        objectTypes: objectTypes,
      );
    }
    final degradeSignals = <SearchDegradeSignal>[];
    final includeCircleGroups = objectTypes.contains(
      SearchObjectType.circleGroup,
    );
    final includeCircles = objectTypes.contains(SearchObjectType.circleCircle);
    final hits = <SearchHit>[];

    if (includeCircleGroups) {
      SearchResolvedFrom groupResolvedFrom = SearchResolvedFrom.remote;
      List<LocalCircleGroupSnapshotRecord> remoteGroups =
          const <LocalCircleGroupSnapshotRecord>[];
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
        title: _sectionTitle('groups', '讨论'),
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

  Future<_SectionBuildResult?> _buildSuggestedGroupsSection(
    SearchRequest request, {
    required LocalSearchNamespace? namespace,
    required Set<SearchObjectType> objectTypes,
  }) async {
    if (namespace == null) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'groups',
          title: _sectionTitle('groups', '讨论'),
          objectTypes: objectTypes
              .where(
                (type) =>
                    type == SearchObjectType.circleGroup ||
                    type == SearchObjectType.circleCircle,
              )
              .toList(growable: false),
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'circle_group_local_namespace_unavailable',
            message: '当前无法确认本地账号命名空间，讨论联想已结算。',
            objectType: SearchObjectType.circleGroup,
          ),
        ],
      );
    }
    try {
      final groups = await _localCircleGroupSnapshotStore.searchGroups(
        namespace: namespace,
        query: request.query,
        limit: request.limit,
      );
      final hits = groups
          .map(
            (group) =>
                _circleGroupHit(group, SearchResolvedFrom.local, request.query),
          )
          .toList(growable: false);
      return _SectionBuildResult(
        section: SearchSection(
          id: 'groups',
          title: _sectionTitle('groups', '讨论'),
          objectTypes: const <SearchObjectType>[SearchObjectType.circleGroup],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.local,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'groups',
          title: _sectionTitle('groups', '讨论'),
          objectTypes: const <SearchObjectType>[SearchObjectType.circleGroup],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.local,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'circle_group_local_failed',
            message: '讨论本地索引读取失败，当前单域已结算。',
            objectType: SearchObjectType.circleGroup,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildContentSection(
    SearchRequest request,
  ) async {
    try {
      final hits = <SearchHit>[];
      if (request.contentTypes.isEmpty) {
        final items = await _contentPostSearchRepository.searchPosts(
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
          final items = await _contentPostSearchRepository.searchPosts(
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
              payload: SearchHitPayloadWireMap(item.toMap()),
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
      final slice = await _locationSearchReader.searchLocations(
        LocationSearchQueryParams(query: request.query, limit: request.limit),
      );
      final hits = slice.items
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

  // location.place（R-S05e 一方地点）：被内容引用但未绑定实体主页的自由文本地点。
  // 端云一体下云侧由 content `place_snapshots` 投影；mock/local 扇出复用 integration
  // POI 作为本地近似种子（仅 mock 路径；beta/gamma/prod 走 RemoteSearchRepository 读
  // 真实 place_snapshots，不读此处）。与 entity.homepage（已绑定实体）互为单一真相源。
  Future<_SectionBuildResult?> _buildPlaceSection(SearchRequest request) async {
    try {
      final slice = await _locationSearchReader.searchLocations(
        LocationSearchQueryParams(query: request.query, limit: request.limit),
      );
      final hits = slice.items
          .map(
            (item) => SearchHit(
              objectType: SearchObjectType.locationPlace,
              objectId: item.id,
              title: item.name,
              subtitle: _string(item.address),
              snippet: _string(item.address),
              resolvedFrom: SearchResolvedFrom.remote,
              matchedField: _matchesText(request.query, <Object?>[item.address])
                  ? 'address'
                  : 'name',
              payload: SearchHitPayloadWireMap(item.toMap()),
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
          objectTypes: const <SearchObjectType>[SearchObjectType.locationPlace],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'locations',
          title: _sectionTitle('locations', '位置'),
          objectTypes: const <SearchObjectType>[SearchObjectType.locationPlace],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'location_place_local_failed',
            message: '一方地点本地检索失败，当前已 fail-closed。',
            objectType: SearchObjectType.locationPlace,
          ),
        ],
      );
    }
  }

  Future<_SectionBuildResult?> _buildUserProfileSection(
    SearchRequest request,
  ) async {
    try {
      final items = await _userProfileRepository.searchSocialRelations(
        query: request.query,
        limit: request.limit,
      );
      final hits = items
          .map(
            (item) => SearchHit(
              objectType: SearchObjectType.userProfile,
              objectId: item.subAccountId,
              title: item.displayName,
              subtitle: item.headline,
              snippet: item.relationshipCapability.canOpenConversation
                  ? '已连接'
                  : '推荐关注',
              resolvedFrom: SearchResolvedFrom.remote,
              matchedField: 'displayName',
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'subAccountId': item.subAccountId,
                'username': item.username,
                'displayName': item.displayName,
                'avatarUrl': item.avatarUrl,
                'headline': item.headline,
                'chatAvailable': item.chatAvailable,
                'relationshipCapability': <String, dynamic>{
                  'relationState': item.relationshipCapability.relationState,
                  'canFollow': item.relationshipCapability.canFollow,
                  'canUnfollow': item.relationshipCapability.canUnfollow,
                  'canOpenConversation':
                      item.relationshipCapability.canOpenConversation,
                  'canStartVoiceCall':
                      item.relationshipCapability.canStartVoiceCall,
                  'canStartVideoCall':
                      item.relationshipCapability.canStartVideoCall,
                },
              }),
            ),
          )
          .where((item) => item.objectId.isNotEmpty && item.title.isNotEmpty)
          .toList(growable: false);
      if (hits.isEmpty) {
        return null;
      }
      return _SectionBuildResult(
        section: SearchSection(
          id: 'users',
          title: _sectionTitle('users', '人'),
          objectTypes: const <SearchObjectType>[SearchObjectType.userProfile],
          hits: hits,
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      );
    } catch (_) {
      return _SectionBuildResult(
        section: SearchSection(
          id: 'users',
          title: _sectionTitle('users', '人'),
          objectTypes: const <SearchObjectType>[SearchObjectType.userProfile],
          hits: const <SearchHit>[],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
        degradeSignals: const <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: 'user_profile_remote_failed',
            message: '用户搜索远端请求失败，当前已 fail-closed。',
            objectType: SearchObjectType.userProfile,
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

  Future<List<LocalCircleGroupSnapshotRecord>> _searchRemoteCircleGroups(
    SearchRequest request,
  ) async {
    final candidateCircles = await _circleRepository.listCircles(limit: 12);
    final merged = <String, LocalCircleGroupSnapshotRecord>{};
    for (final circle in candidateCircles) {
      final circleId = circle.id.trim();
      if (circleId.isEmpty) {
        continue;
      }
      final circleName = circle.name.trim();
      CircleGroupPageSlice groups;
      try {
        groups = await _circleGroupQuery.search(
          CircleGroupSearchQuery(
            circleId: circleId,
            query: request.query,
            limit: request.limit,
          ),
        );
      } catch (_) {
        continue;
      }
      for (final g in groups.items) {
        final payload = LocalCircleGroupSnapshotRecord.fromGroupSlice(
          g,
          circleName: circleName,
        );
        final groupId = payload.groupId;
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
    LocalCircleGroupSnapshotRecord payload,
    SearchResolvedFrom resolvedFrom,
    String query,
  ) {
    final normalizedPayload = payload.toStorageMap();
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
      payload: SearchHitPayloadWireMap(normalizedPayload),
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
      payload: SearchHitPayloadCircleCircle(item),
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
      payload: SearchHitPayloadWireMap(item.toMap()),
    );
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
      subtitle: item.authorDisplayName,
      snippet: item.summary,
      resolvedFrom: resolvedFrom,
      matchedField: item.matchedField,
      payload: SearchHitPayloadContentPost(item),
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
      'senderPersonaId': message.senderPersonaId,
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

extension SearchHitTypedViews on SearchHit {
  PostSearchItemView? get asContentPostItem {
    final p = payload;
    return p is SearchHitPayloadContentPost ? p.item : null;
  }

  CircleSearchItemView? get asCircleCircleItem {
    final p = payload;
    return p is SearchHitPayloadCircleCircle ? p.item : null;
  }
}
