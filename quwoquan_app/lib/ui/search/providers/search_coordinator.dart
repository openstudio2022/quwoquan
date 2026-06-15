import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

final searchCoordinatorProvider = NotifierProvider.autoDispose
    .family<SearchCoordinator, SearchSessionState, SearchLaunchContext>(
      SearchCoordinator.new,
    );

class SearchCoordinator extends Notifier<SearchSessionState> {
  SearchCoordinator(this._launchContext);

  final SearchLaunchContext _launchContext;

  @override
  SearchSessionState build() {
    ref.onDispose(() {
      _debounceTimer?.cancel();
    });
    final initial = SearchSessionState(
      launchContext: _launchContext,
      query: _launchContext.prefilledQuery,
      scope: _launchContext.initialScope,
      selection: _resolveInitialSelection(_launchContext),
    );
    Future.microtask(() {
      if (!ref.mounted) {
        return;
      }
      unawaited(hydrateRecentSearches());
      unawaited(hydrateSearchInspiration());
      if (state.hasQuery) {
        scheduleSearch(immediate: true);
      }
    });
    return initial;
  }

  static const Duration _searchDebounce = Duration(milliseconds: 180);
  static const int _collapsedContactsCount = 4;
  static const int _collapsedChatRecordsCount = 3;
  static const int _conversationSearchLimit = 12;
  static const int _maxNetworkSuggestions = 6;

  final SearchRecentHistoryStore _localStore = const SearchRecentHistoryStore();

  Timer? _debounceTimer;
  int _searchRequestToken = 0;

  static SearchObjectSelection _resolveInitialSelection(
    SearchLaunchContext launchContext,
  ) {
    final explicitSelection = launchContext.searchObjectSelection.normalized();
    if (!explicitSelection.isEmpty) {
      return explicitSelection;
    }
    final facetSelection = SearchObjectSelection.fromFacet(
      launchContext.initialFacet,
    );
    if (!facetSelection.isEmpty) {
      return facetSelection;
    }
    return SearchObjectSelection.fromSearchScope(launchContext.initialScope);
  }

  void _setState(SearchSessionState next) {
    if (!ref.mounted) {
      return;
    }
    state = next;
  }

  void updateQuery(String query, {bool immediate = false}) {
    final trimmedQuery = query.trim();
    _debounceTimer?.cancel();
    _setState(
      state.copyWith(
        query: query,
        isManagingHistory: false,
        areContactsExpanded: false,
        areChatRecordsExpanded: false,
        suggestionSections: trimmedQuery.isEmpty
            ? const <SearchSuggestionSection>[]
            : state.suggestionSections,
        isLoading: trimmedQuery.isEmpty ? false : state.isLoading,
      ),
    );
    if (trimmedQuery.isEmpty) {
      return;
    }
    scheduleSearch(immediate: immediate);
  }

  void updateSelection(SearchObjectSelection selection) {
    final normalizedSelection = selection.normalized();
    if (setEquals(
          state.selection.normalizedTargets,
          normalizedSelection.normalizedTargets,
        ) &&
        setEquals(
          state.selection.contentTypes,
          normalizedSelection.contentTypes,
        )) {
      return;
    }
    _setState(
      state.copyWith(
        selection: normalizedSelection,
        launchContext: state.launchContext.copyWith(
          searchObjectSelection: normalizedSelection,
          initialFacet: normalizedSelection.toFacet(),
        ),
      ),
    );
    if (state.hasQuery) {
      scheduleSearch(immediate: true);
    }
  }

  void startManagingHistory() {
    if (state.hasQuery || state.recentSearches.isEmpty) {
      return;
    }
    _setState(state.copyWith(isManagingHistory: true, isHistoryExpanded: true));
  }

  void finishManagingHistory() {
    _setState(
      state.copyWith(isManagingHistory: false, isHistoryExpanded: false),
    );
  }

  void toggleHistoryExpanded() {
    if (state.recentSearches.isEmpty) {
      return;
    }
    _setState(state.copyWith(isHistoryExpanded: !state.isHistoryExpanded));
  }

  void expandContacts() {
    if (state.areContactsExpanded) {
      return;
    }
    _setState(
      state.copyWith(
        areContactsExpanded: true,
        suggestionSections: _applyExpansionFlags(
          state.suggestionSections,
          contactsExpanded: true,
        ),
      ),
    );
  }

  void expandChatRecords() {
    if (state.areChatRecordsExpanded) {
      return;
    }
    _setState(
      state.copyWith(
        areChatRecordsExpanded: true,
        suggestionSections: _applyExpansionFlags(
          state.suggestionSections,
          chatRecordsExpanded: true,
        ),
      ),
    );
  }

  void scheduleSearch({bool immediate = false}) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(_performSearch());
      return;
    }
    _debounceTimer = Timer(_searchDebounce, () => unawaited(_performSearch()));
  }

  Future<void> hydrateRecentSearches() async {
    _setState(state.copyWith(isHydratingHistory: true));
    final localEntries = await _localStore.load();
    if (ref.mounted && localEntries.isNotEmpty) {
      _setState(state.copyWith(recentSearches: localEntries));
    }
    try {
      final remoteEntries = await ref
          .read(userProfileRepositoryProvider)
          .listRecentSearches();
      final merged = _mergeHistory(localEntries, remoteEntries);
      if (!ref.mounted) {
        return;
      }
      _setState(
        state.copyWith(recentSearches: merged, isHydratingHistory: false),
      );
      await _localStore.save(merged);
      final remoteKeys = remoteEntries.map(_historyKeyForEntry).toSet();
      for (final entry in localEntries) {
        if (remoteKeys.contains(_historyKeyForEntry(entry))) {
          continue;
        }
        unawaited(
          ref
              .read(userProfileRepositoryProvider)
              .upsertRecentSearch(
                query: entry.query,
                scope: entry.scope,
                facet: entry.facet,
              ),
        );
      }
    } catch (_) {
      if (!ref.mounted) {
        return;
      }
      _setState(state.copyWith(isHydratingHistory: false));
    }
  }

  Future<void> hydrateSearchInspiration() async {
    _setState(
      state.copyWith(inspiration: state.inspiration.copyWith(isLoading: true)),
    );
    try {
      final circles = await ref
          .read(circleRepositoryProvider)
          .listCircles(limit: 9);
      final homepageRepository = ref.read(homepageRepositoryProvider);
      var locations = await homepageRepository.searchHomepages(
        query: '',
        homepageType: 'location',
        limit: 9,
      );
      if (locations.isEmpty) {
        locations = await homepageRepository.searchHomepages(
          query: '',
          limit: 9,
        );
      }
      final currentUserId = ref.read(currentUserIdProvider).trim();
      final effectiveUserId = currentUserId.isNotEmpty
          ? currentUserId
          : 'current_user';
      final people = await ref
          .read(userProfileRepositoryProvider)
          .listFollowing(effectiveUserId, limit: 4);
      final todaySeeds = <SearchInspirationChipView>[
        ...circles
            .take(2)
            .map(
              (item) => SearchInspirationChipView(
                title: item.name,
                subtitle:
                    '${_positiveCount(item.weeklyActiveCount, item.memberCount)}个交集',
                query: item.name,
              ),
            ),
        ...locations
            .take(2)
            .map(
              (item) => SearchInspirationChipView(
                title: item.title,
                subtitle: '地点交集',
                query: item.title,
              ),
            ),
      ].where((item) => item.title.trim().isNotEmpty).take(4).toList(growable: false);

      if (!ref.mounted) {
        return;
      }
      _setState(
        state.copyWith(
          inspiration: SearchInspirationState(
            todayIntersections: todaySeeds,
            hotCircles: circles
                .where((item) => item.name.trim().isNotEmpty)
                .take(6)
                .map(
                  (item) => SearchInspirationCardView(
                    id: item.id,
                    title: item.name,
                    subtitle:
                        '${_positiveCount(item.memberCount, item.weeklyActiveCount)}人',
                    coverUrl: item.coverUrl,
                    query: item.name,
                  ),
                )
                .toList(growable: false),
            hotLocations: locations
                .where((item) => item.title.trim().isNotEmpty)
                .take(6)
                .map(
                  (item) => SearchInspirationCardView(
                    id: item.id,
                    title: item.title,
                    subtitle: (item.city ?? item.address ?? '地点').trim(),
                    coverUrl: item.coverUrl,
                    query: item.title,
                  ),
                )
                .toList(growable: false),
            people: people
                .where((item) => item.displayName.trim().isNotEmpty)
                .take(4)
                .map(
                  (item) => SearchInspirationPersonView(
                    id: item.subAccountId,
                    displayName: item.displayName,
                    avatarUrl: item.avatarUrl,
                    headline: item.isFollowing ? '已关注' : '摄影圈活跃',
                    reason: '共同兴趣 3 个',
                  ),
                )
                .toList(growable: false),
          ),
        ),
      );
    } catch (_) {
      if (!ref.mounted) {
        return;
      }
      _setState(
        state.copyWith(
          inspiration: state.inspiration.copyWith(isLoading: false),
        ),
      );
    }
  }

  int _positiveCount(int primary, int secondary) {
    if (primary > 0) {
      return primary;
    }
    if (secondary > 0) {
      return secondary;
    }
    return 1;
  }

  Future<void> useRecentSearch(RecentSearchEntryView entry) async {
    final facetSelection = SearchObjectSelection.fromFacet(entry.facet);
    final selection = facetSelection.isEmpty
        ? SearchObjectSelection.fromSearchScope(entry.scope)
        : facetSelection;
    _setState(
      state.copyWith(
        query: entry.query,
        scope: entry.scope,
        selection: selection,
        launchContext: state.launchContext.copyWith(
          initialScope: entry.scope,
          initialFacet: selection.toFacet(),
          searchObjectSelection: selection,
        ),
        isManagingHistory: false,
        isHistoryExpanded: false,
        areContactsExpanded: false,
        areChatRecordsExpanded: false,
      ),
    );
    scheduleSearch(immediate: true);
  }

  Future<void> rememberCurrentQuery({String? query}) {
    return _rememberQuery(query: query ?? state.query);
  }

  Future<void> removeRecentSearch(String entryId) async {
    final nextEntries = state.recentSearches
        .where((entry) => entry.entryId != entryId)
        .toList(growable: false);
    _setState(
      state.copyWith(
        recentSearches: nextEntries,
        isManagingHistory: nextEntries.isEmpty
            ? false
            : state.isManagingHistory,
        isHistoryExpanded: nextEntries.isEmpty
            ? false
            : state.isHistoryExpanded,
      ),
    );
    await _localStore.save(nextEntries);
    try {
      await ref.read(userProfileRepositoryProvider).deleteRecentSearch(entryId);
    } catch (_) {
      // Keep local-first delete even when remote cleanup fails.
    }
  }

  Future<void> clearRecentSearches() async {
    _setState(
      state.copyWith(
        recentSearches: const <RecentSearchEntryView>[],
        isManagingHistory: false,
        isHistoryExpanded: false,
      ),
    );
    await _localStore.clear();
    try {
      await ref.read(userProfileRepositoryProvider).clearRecentSearches();
    } catch (_) {
      // Keep local-first clear even when remote cleanup fails.
    }
  }

  Future<void> _performSearch() async {
    final query = state.query.trim();
    if (query.isEmpty) {
      _setState(
        state.copyWith(
          isLoading: false,
          suggestionSections: const <SearchSuggestionSection>[],
        ),
      );
      return;
    }
    final token = ++_searchRequestToken;
    _setState(state.copyWith(isLoading: true));
    final sections = await _buildSuggestionSections(query);
    if (!ref.mounted || token != _searchRequestToken) {
      return;
    }
    _setState(state.copyWith(suggestionSections: sections, isLoading: false));
  }

  Future<List<SearchSuggestionSection>> _buildSuggestionSections(
    String query,
  ) async {
    final normalizedQuery = query.trim();
    if (normalizedQuery.isEmpty) {
      return const <SearchSuggestionSection>[];
    }

    final selection = state.selection.normalized();
    final objectTarget = selection.activeObjectTarget;
    final includesContacts =
        objectTarget == null || objectTarget == SearchObjectTarget.contacts;
    final includesDirectChats =
        objectTarget == null || objectTarget == SearchObjectTarget.directChats;
    final includesGroupChats =
        objectTarget == null || objectTarget == SearchObjectTarget.groupChats;
    final includesChatRecords = includesDirectChats || includesGroupChats;
    final includesCircles =
        objectTarget == null || objectTarget == SearchObjectTarget.circles;
    final includesNetwork = selection.enabledContentTypes.isNotEmpty;
    final response = await ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: normalizedQuery,
            mode: SearchMode.suggest,
            objectTypes: _searchObjectTypesForSelection(selection),
            limit: _conversationSearchLimit,
            conversationType: _conversationTypeForSelection(objectTarget),
          ),
        );

    final responseHits = _hitsFromResponse(response);
    final contacts = responseHits
        .where((hit) => hit.objectType == SearchObjectType.chatContact)
        .map((hit) => ChatContactSearchItemDto.fromMap(hit.payload.toWireMap()))
        .toList(growable: false);
    final conversationHits = responseHits
        .where((hit) => hit.objectType == SearchObjectType.chatConversation)
        .map(
          (hit) => ConversationSearchItemView.fromMap(hit.payload.toWireMap()),
        )
        .toList(growable: false);
    final messageHits = responseHits
        .where((hit) => hit.objectType == SearchObjectType.chatMessage)
        .map((hit) => MessageSearchItemView.fromMap(hit.payload.toWireMap()))
        .toList(growable: false);
    final circleSuggestions = includesCircles
        ? responseHits
              .where((hit) => hit.objectType == SearchObjectType.circleGroup)
              .map(
                (hit) =>
                    hit.asCircleCircleItem ??
                    CircleSearchItemView.fromMap(hit.payload.toWireMap()),
              )
              .toList(growable: false)
        : const <CircleSearchItemView>[];
    final locationSuggestions = responseHits
        .where(
          (hit) => hit.objectType == SearchObjectType.integrationLocationPoi,
        )
        .map((hit) => LocationPoiDto.fromMap(hit.payload.toWireMap()))
        .where((item) => item.name.trim().isNotEmpty)
        .toList(growable: false);
    final followedPeopleSuggestions = responseHits
        .where((hit) => hit.objectType == SearchObjectType.userProfile)
        .map(
          (hit) =>
              SocialRelationSearchItemView.fromMap(hit.payload.toWireMap()),
        )
        .where(
          (item) =>
              item.relationshipCapability.canOpenConversation ||
              item.relationshipCapability.canUnfollow,
        )
        .where((item) => item.displayName.trim().isNotEmpty)
        .toList(growable: false);
    final allConversations = ref
        .read(conversationCacheProvider)
        .getAll()
        .map((item) => item.toConversationSearchItemView())
        .toList(growable: false);
    final seededConversations = <String, ConversationSearchItemView>{
      for (final item in allConversations) item.conversationId: item,
      for (final item in conversationHits) item.conversationId: item,
    }.values.toList(growable: false);
    final chatRepo = ref.read(chatRepositoryProvider);
    final contactSuggestions = await _buildContactSuggestions(
      contacts: contacts,
      allConversations: seededConversations,
      chatRepo: chatRepo,
    );
    final chatRecordSuggestions = _buildChatRecordSuggestions(
      conversationHits: conversationHits,
      messageHits: messageHits,
      allConversations: seededConversations,
    );
    final filteredChatRecordSuggestions = chatRecordSuggestions
        .where((item) {
          if (_isGroupConversation(item.conversationType)) {
            return includesGroupChats;
          }
          return includesDirectChats;
        })
        .toList(growable: false);
    final networkSuggestions = includesNetwork
        ? _buildNetworkSuggestions(normalizedQuery)
        : const <NetworkSearchSuggestion>[];

    final sections = <SearchSuggestionSection>[
      if (includesContacts && contactSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.contacts,
          items: contactSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.contact)
              .toList(growable: false),
          expanded: state.areContactsExpanded,
          collapsedItemCount: _collapsedContactsCount,
          moreLabel: '更多联系人',
        ),
      if (includesChatRecords && filteredChatRecordSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.chatRecords,
          items: filteredChatRecordSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.chatRecord)
              .toList(growable: false),
          expanded: state.areChatRecordsExpanded,
          collapsedItemCount: _collapsedChatRecordsCount,
          moreLabel: switch (objectTarget) {
            SearchObjectTarget.directChats => '更多单聊',
            SearchObjectTarget.groupChats => '更多讨论',
            _ => '更多聊天记录',
          },
          titleOverride: switch (objectTarget) {
            SearchObjectTarget.directChats => '单聊',
            SearchObjectTarget.groupChats => '讨论',
            _ => null,
          },
        ),
      if (includesCircles && circleSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.circles,
          items: circleSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.circle)
              .toList(growable: false),
        ),
      if (locationSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.locations,
          items: locationSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.location)
              .toList(growable: false),
        ),
      if (followedPeopleSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.followedPeople,
          items: followedPeopleSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.followedPerson)
              .toList(growable: false),
        ),
      if (includesNetwork)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.network,
          items: networkSuggestions
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.network)
              .toList(growable: false),
        ),
    ];
    return _applyExpansionFlags(sections);
  }

  Iterable<SearchHit> _hitsFromResponse(SearchResponse response) {
    if (response.hits.isNotEmpty) {
      return response.hits;
    }
    return response.sections.expand((section) => section.hits);
  }

  bool _isGroupConversation(String? conversationType) {
    return conversationType?.trim().toLowerCase() == 'group';
  }

  Set<SearchObjectType> _searchObjectTypesForSelection(
    SearchObjectSelection selection,
  ) {
    final objectTarget = selection.activeObjectTarget;
    return switch (objectTarget) {
      SearchObjectTarget.contacts => <SearchObjectType>{
        SearchObjectType.chatContact,
      },
      SearchObjectTarget.directChats ||
      SearchObjectTarget.groupChats => <SearchObjectType>{
        SearchObjectType.chatConversation,
        SearchObjectType.chatMessage,
      },
      SearchObjectTarget.circles => <SearchObjectType>{
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
      },
      null => <SearchObjectType>{
        SearchObjectType.chatContact,
        SearchObjectType.chatConversation,
        SearchObjectType.chatMessage,
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
        SearchObjectType.integrationLocationPoi,
        SearchObjectType.userProfile,
      },
    };
  }

  String? _conversationTypeForSelection(SearchObjectTarget? target) {
    return switch (target) {
      SearchObjectTarget.directChats => 'direct',
      SearchObjectTarget.groupChats => 'group',
      _ => null,
    };
  }

  List<SearchSuggestionSection> _applyExpansionFlags(
    List<SearchSuggestionSection> sections, {
    bool? contactsExpanded,
    bool? chatRecordsExpanded,
  }) {
    final nextContactsExpanded = contactsExpanded ?? state.areContactsExpanded;
    final nextChatRecordsExpanded =
        chatRecordsExpanded ?? state.areChatRecordsExpanded;
    return sections
        .map((section) {
          switch (section.kind) {
            case SearchSuggestionSectionKind.contacts:
              return section.copyWith(expanded: nextContactsExpanded);
            case SearchSuggestionSectionKind.chatRecords:
              return section.copyWith(expanded: nextChatRecordsExpanded);
            case SearchSuggestionSectionKind.circles:
            case SearchSuggestionSectionKind.locations:
            case SearchSuggestionSectionKind.followedPeople:
            case SearchSuggestionSectionKind.network:
              return section;
          }
        })
        .toList(growable: false);
  }

  Future<List<ContactSearchSuggestion>> _buildContactSuggestions({
    required List<ChatContactSearchItemDto> contacts,
    required List<ConversationSearchItemView> allConversations,
    required ChatRepository chatRepo,
  }) async {
    final suggestions = <ContactSearchSuggestion>[];
    for (final contact in contacts) {
      final userId = contact.contactId.trim();
      final displayName = contact.displayName.trim();
      if (userId.isEmpty || displayName.isEmpty) {
        continue;
      }
      final directConversationId = contact.conversationId?.trim() ?? '';
      suggestions.add(
        ContactSearchSuggestion(
          contactId: userId,
          displayName: displayName,
          conversationId: directConversationId.isNotEmpty
              ? directConversationId
              : await _resolveContactConversationId(
                  displayName: displayName,
                  userId: userId,
                  allConversations: allConversations,
                  chatRepo: chatRepo,
                ),
          avatarUrl: contact.avatarUrl,
          subtitle: contact.subtitle ?? '联系人',
        ),
      );
    }
    return suggestions;
  }

  Future<String> _resolveContactConversationId({
    required String displayName,
    required String userId,
    required List<ConversationSearchItemView> allConversations,
    required ChatRepository chatRepo,
  }) async {
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
      final members = await chatRepo.listMemberUserIds(
        conversation.conversationId,
      );
      final containsUser = members.contains(userId);
      if (!containsUser) {
        continue;
      }
      final isDirectLike =
          conversation.type == 'direct' || conversation.type == 'encrypted';
      if (isDirectLike) {
        return conversation.conversationId;
      }
    }
    for (final conversation in allConversations) {
      final members = await chatRepo.listMemberUserIds(
        conversation.conversationId,
      );
      if (members.contains(userId)) {
        return conversation.conversationId;
      }
    }
    return allConversations.isNotEmpty
        ? allConversations.first.conversationId
        : '';
  }

  List<ChatRecordSearchSuggestion> _buildChatRecordSuggestions({
    required List<ConversationSearchItemView> conversationHits,
    required List<MessageSearchItemView> messageHits,
    required List<ConversationSearchItemView> allConversations,
  }) {
    final conversationIndex = <String, ConversationSearchItemView>{
      for (final conversation in allConversations)
        conversation.conversationId: conversation,
    };
    final accumulators = <String, _ChatRecordAccumulator>{};

    for (final conversation in conversationHits) {
      final accumulator = accumulators.putIfAbsent(
        conversation.conversationId,
        () => _ChatRecordAccumulator.fromConversation(conversation),
      );
      accumulator.includeConversationHit(conversation);
    }

    for (final message in messageHits) {
      final seedConversation = conversationIndex[message.conversationId];
      final accumulator = accumulators.putIfAbsent(
        message.conversationId,
        () => _ChatRecordAccumulator.fromMessage(
          message,
          seedConversation: seedConversation,
        ),
      );
      accumulator.includeMessageHit(message);
    }

    final results = accumulators.values
        .map((accumulator) => accumulator.build())
        .toList(growable: false);
    results.sort((left, right) {
      final countCompare = right.matchCount.compareTo(left.matchCount);
      if (countCompare != 0) {
        return countCompare;
      }
      final leftTime = left.timestamp;
      final rightTime = right.timestamp;
      if (leftTime == null && rightTime == null) {
        return left.conversationTitle.compareTo(right.conversationTitle);
      }
      if (leftTime == null) {
        return 1;
      }
      if (rightTime == null) {
        return -1;
      }
      return rightTime.compareTo(leftTime);
    });
    return results;
  }

  List<NetworkSearchSuggestion> _buildNetworkSuggestions(String query) {
    final seeds = <NetworkSearchSuggestion>[
      NetworkSearchSuggestion(
        query: query,
        title: query,
        subtitle: '搜索全部结果',
        initialTabId: 'all',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: '$query 交集',
        subtitle: '查看最值得连接的结果',
        initialTabId: 'intersection',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: '$query 图片',
        subtitle: '只看图片结果',
        initialTabId: 'image',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: '$query 视频',
        subtitle: '只看视频结果',
        initialTabId: 'video',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: '$query 长文',
        subtitle: '只看长文结果',
        initialTabId: 'article',
      ),
    ];
    final unique = <String>{};
    return seeds
        .where(
          (item) =>
              unique.add('${item.query.trim()}::${item.initialTabId ?? ''}'),
        )
        .take(_maxNetworkSuggestions)
        .toList(growable: false);
  }

  Future<void> _rememberQuery({required String query}) async {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final selectionFacet = state.selection.toFacet();
    final historyScope = _scopeForSelection(state.selection);
    final now = DateTime.now();
    final localEntry = RecentSearchEntryView(
      entryId: RecentSearchEntryView.buildEntryId(
        query: trimmedQuery,
        scope: historyScope,
        facet: selectionFacet,
      ),
      query: trimmedQuery,
      scope: historyScope,
      facet: selectionFacet,
      updatedAt: now,
    );
    final merged = _mergeHistory(<RecentSearchEntryView>[
      localEntry,
    ], state.recentSearches);
    _setState(state.copyWith(recentSearches: merged));
    await _localStore.save(merged);
    try {
      final remoteEntry = await ref
          .read(userProfileRepositoryProvider)
          .upsertRecentSearch(
            query: trimmedQuery,
            scope: historyScope,
            facet: selectionFacet,
          );
      final nextEntries = _mergeHistory(<RecentSearchEntryView>[
        remoteEntry,
      ], merged);
      if (!ref.mounted) {
        return;
      }
      _setState(state.copyWith(recentSearches: nextEntries));
      await _localStore.save(nextEntries);
    } catch (_) {
      // Local-first history remains available while remote sync degrades.
    }
  }

  List<RecentSearchEntryView> _mergeHistory(
    List<RecentSearchEntryView> primary,
    List<RecentSearchEntryView> secondary,
  ) {
    final merged = <String, RecentSearchEntryView>{};
    for (final entry in [...primary, ...secondary]) {
      final key = _historyKeyForEntry(entry);
      final existing = merged[key];
      if (existing == null || entry.updatedAt.isAfter(existing.updatedAt)) {
        merged[key] = entry;
      }
    }
    final values = merged.values.toList(growable: false);
    values.sort((left, right) => right.updatedAt.compareTo(left.updatedAt));
    return values.take(15).toList(growable: false);
  }

  String _historyKeyForEntry(RecentSearchEntryView entry) {
    return '${entry.scope.wireValue}|${entry.facet ?? ''}|${entry.query.toLowerCase()}';
  }

  SearchScope _scopeForSelection(SearchObjectSelection selection) {
    switch (selection.normalized().activeObjectTarget) {
      case SearchObjectTarget.contacts:
        return SearchScope.socialRelation;
      case SearchObjectTarget.directChats:
      case SearchObjectTarget.groupChats:
        return SearchScope.messages;
      case SearchObjectTarget.circles:
        return SearchScope.circles;
      case null:
        return SearchScope.all;
    }
  }
}

class SearchRecentHistoryStore {
  const SearchRecentHistoryStore();

  static const String _storageKey = 'global_search_recent_entries_v1';

  Future<List<RecentSearchEntryView>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.trim().isEmpty) {
      return const <RecentSearchEntryView>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <RecentSearchEntryView>[];
      }
      return decoded
          .whereType<Map>()
          .map(
            (item) =>
                RecentSearchEntryView.fromMap(item.cast<String, dynamic>()),
          )
          .where((item) => item.query.trim().isNotEmpty)
          .toList(growable: false);
    } catch (_) {
      return const <RecentSearchEntryView>[];
    }
  }

  Future<void> save(List<RecentSearchEntryView> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _storageKey,
      jsonEncode(entries.map((entry) => entry.toMap()).toList(growable: false)),
    );
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_storageKey);
  }
}

class _ChatRecordAccumulator {
  _ChatRecordAccumulator({
    required this.conversationId,
    required this.conversationTitle,
    required this.conversationType,
    required this.avatarUrl,
    required this.matchedPreview,
    required this.matchCount,
    this.messageAnchorId,
    this.timestamp,
  });

  factory _ChatRecordAccumulator.fromConversation(
    ConversationSearchItemView conversation,
  ) {
    return _ChatRecordAccumulator(
      conversationId: conversation.conversationId,
      conversationTitle: conversation.title,
      conversationType: conversation.type,
      avatarUrl: conversation.avatarUrl,
      matchedPreview:
          conversation.highlightText ??
          conversation.lastMessagePreview ??
          '打开聊天',
      matchCount: 1,
      timestamp: conversation.lastMessageTime,
    );
  }

  factory _ChatRecordAccumulator.fromMessage(
    MessageSearchItemView message, {
    ConversationSearchItemView? seedConversation,
  }) {
    // 会话头像只保留 authoritative conversation avatar；
    // direct/group 的成员回退统一由共享 ConversationAvatar 组件负责。
    return _ChatRecordAccumulator(
      conversationId: message.conversationId,
      conversationTitle:
          message.conversationTitle ?? seedConversation?.title ?? '聊天记录',
      conversationType: seedConversation?.type ?? 'group',
      avatarUrl: message.conversationAvatarUrl ?? seedConversation?.avatarUrl,
      matchedPreview: message.highlightText ?? message.contentPreview,
      matchCount: 1,
      messageAnchorId: message.messageId,
      timestamp: message.timestamp,
    );
  }

  final String conversationId;
  String conversationTitle;
  String conversationType;
  String? avatarUrl;
  String matchedPreview;
  int matchCount;
  String? messageAnchorId;
  DateTime? timestamp;

  void includeConversationHit(ConversationSearchItemView conversation) {
    conversationTitle = conversation.title;
    conversationType = conversation.type;
    avatarUrl = avatarUrl ?? conversation.avatarUrl;
    matchedPreview =
        conversation.highlightText ??
        conversation.lastMessagePreview ??
        matchedPreview;
    timestamp = _maxTimestamp(timestamp, conversation.lastMessageTime);
  }

  void includeMessageHit(MessageSearchItemView message) {
    matchCount += 1;
    matchedPreview = message.highlightText ?? message.contentPreview;
    messageAnchorId ??= message.messageId;
    timestamp = _maxTimestamp(timestamp, message.timestamp);
    avatarUrl = avatarUrl ?? message.conversationAvatarUrl;
  }

  ChatRecordSearchSuggestion build() {
    return ChatRecordSearchSuggestion(
      conversationId: conversationId,
      conversationTitle: conversationTitle,
      conversationType: conversationType,
      matchedPreview: matchedPreview,
      matchCount: matchCount,
      avatarUrl: avatarUrl,
      messageAnchorId: messageAnchorId,
      timestamp: timestamp,
    );
  }

  DateTime? _maxTimestamp(DateTime? left, DateTime? right) {
    if (left == null) {
      return right;
    }
    if (right == null) {
      return left;
    }
    return left.isAfter(right) ? left : right;
  }
}
