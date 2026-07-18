part of 'search_coordinator.dart';

extension SearchCoordinatorSuggestions on SearchCoordinator {
  void _invalidateActiveSearch() {
    _searchRequestToken += 1;
    _waitController.cancel();
  }

  bool _isCurrentSearch(int token, int generation) {
    return _isMounted &&
        token == _searchRequestToken &&
        _waitController.isCurrent(generation);
  }

  bool _allowsHomepageSearch(SearchObjectSelection selection) {
    return selection.normalized().enabledContentTypes.isNotEmpty;
  }

  bool _hasBrowsableLocalSuggestions(List<SearchSuggestionSection> sections) {
    return sections.any(
      (section) =>
          section.kind != SearchSuggestionSectionKind.network &&
          section.items.isNotEmpty,
    );
  }

  Future<_SuggestionDomainOutcome> _settleLocalSuggestions({
    required String query,
    required SearchObjectSelection selection,
    required int token,
    required int generation,
    required CloudOperationCancellationSignal cancellation,
  }) async {
    try {
      final result = await _buildSuggestionSections(
        query,
        selection: selection,
        cancellation: cancellation,
      ).timeout(AppRequestWaitTimings.localLookupDeadline);
      if (_isCurrentSearch(token, generation)) {
        final existingHomepagePreviews = _currentState.suggestionSections
            .where(
              (section) => section.kind == SearchSuggestionSectionKind.network,
            )
            .expand((section) => section.items)
            .where(
              (entry) =>
                  entry.kind == SearchSuggestionEntryKind.network &&
                  entry.cast<NetworkSearchSuggestion>().isHomepagePreview,
            )
            .map((entry) => entry.cast<NetworkSearchSuggestion>())
            .toList(growable: false);
        _setState(
          _currentState.copyWith(
            suggestionSections: _mergeHomepagePreviews(
              result.sections,
              existingHomepagePreviews,
            ),
            isSlow: false,
          ),
        );
      }
      return _SuggestionDomainOutcome(error: result.error);
    } catch (error) {
      return _SuggestionDomainOutcome(error: error);
    }
  }

  Future<_SuggestionDomainOutcome> _settleHomepageSuggestions({
    required String query,
    required int token,
    required int generation,
    required CloudOperationCancellationSignal cancellation,
  }) async {
    try {
      final homepages = await _coordinatorRef
          .read(homepageRepositoryProvider)
          .searchHomepages(
            query: query,
            status: 'published',
            limit: SearchCoordinator._localMatchLimit,
            cancellation: cancellation,
            deadlineAt: DateTime.now().add(
              AppRequestWaitTimings.foregroundReadDeadline,
            ),
          );
      if (_isCurrentSearch(token, generation)) {
        final previews = homepages
            .where(
              (item) =>
                  item.id.trim().isNotEmpty && item.title.trim().isNotEmpty,
            )
            .map(
              (item) => NetworkSearchSuggestion(
                query: query,
                title: item.title,
                subtitle:
                    item.subtitle ??
                    item.city ??
                    item.address ??
                    item.homepageType,
                homepageId: item.id,
                coverUrl: item.coverUrl,
              ),
            )
            .toList(growable: false);
        _setState(
          _currentState.copyWith(
            suggestionSections: _mergeHomepagePreviews(
              _currentState.suggestionSections,
              previews,
            ),
            isNetworkLoading: false,
            isSlow: false,
          ),
        );
      }
      return const _SuggestionDomainOutcome();
    } catch (error) {
      return _SuggestionDomainOutcome(
        error: CloudErrorMapper.runtimeFailureFromException(
          error,
          requestPath: EntityApiMetadata.searchHomepagesPath,
        ),
      );
    }
  }

  List<SearchSuggestionSection> _mergeHomepagePreviews(
    List<SearchSuggestionSection> sections,
    List<NetworkSearchSuggestion> previews,
  ) {
    if (previews.isEmpty) return sections;
    final previewEntries = previews
        .map<SearchSuggestionEntry>(SearchSuggestionEntry.network)
        .toList(growable: false);
    final networkIndex = sections.indexWhere(
      (section) => section.kind == SearchSuggestionSectionKind.network,
    );
    if (networkIndex < 0) {
      return <SearchSuggestionSection>[
        ...sections,
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.network,
          items: previewEntries,
        ),
      ];
    }
    final network = sections[networkIndex];
    final merged = <SearchSuggestionEntry>[...previewEntries, ...network.items];
    final next = List<SearchSuggestionSection>.of(sections);
    next[networkIndex] = network.copyWith(items: merged);
    return next;
  }

  Future<_LocalSuggestionResult> _buildSuggestionSections(
    String query, {
    required SearchObjectSelection selection,
    required CloudOperationCancellationSignal cancellation,
  }) async {
    final normalizedQuery = query.trim();
    if (normalizedQuery.isEmpty) {
      return const _LocalSuggestionResult(
        sections: <SearchSuggestionSection>[],
      );
    }

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
    final response = await _coordinatorRef
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: normalizedQuery,
            mode: SearchMode.suggest,
            objectTypes: _searchObjectTypesForSelection(selection),
            limit: SearchCoordinator._conversationSearchLimit,
            conversationType: _conversationTypeForSelection(objectTarget),
          ),
          cancellation: cancellation,
          deadlineAt: DateTime.now().add(
            AppRequestWaitTimings.localLookupDeadline,
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
    final allConversations = _coordinatorRef
        .read(conversationCacheProvider)
        .getAll()
        .map((item) => item.toConversationSearchItemView())
        .toList(growable: false);
    final seededConversations = <String, ConversationSearchItemView>{
      for (final item in allConversations) item.conversationId: item,
      for (final item in conversationHits) item.conversationId: item,
    }.values.toList(growable: false);
    final contactSuggestions = _buildContactSuggestions(
      contacts: contacts,
      allConversations: seededConversations,
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
              .take(SearchCoordinator._localMatchLimit)
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.contact)
              .toList(growable: false),
        ),
      if (includesChatRecords && filteredChatRecordSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.chatRecords,
          items: filteredChatRecordSuggestions
              .take(SearchCoordinator._localMatchLimit)
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.chatRecord)
              .toList(growable: false),
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
              .take(SearchCoordinator._localMatchLimit)
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.circle)
              .toList(growable: false),
        ),
      if (locationSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.locations,
          items: locationSuggestions
              .take(SearchCoordinator._localMatchLimit)
              .map<SearchSuggestionEntry>(SearchSuggestionEntry.location)
              .toList(growable: false),
        ),
      if (followedPeopleSuggestions.isNotEmpty)
        SearchSuggestionSection(
          kind: SearchSuggestionSectionKind.followedPeople,
          items: followedPeopleSuggestions
              .take(SearchCoordinator._localMatchLimit)
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
    return _LocalSuggestionResult(
      sections: _applyExpansionFlags(sections),
      error: response.degradeSignals.isEmpty
          ? null
          : StateError(response.degradeSignals.first.message),
    );
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
    final nextContactsExpanded =
        contactsExpanded ?? _currentState.areContactsExpanded;
    final nextChatRecordsExpanded =
        chatRecordsExpanded ?? _currentState.areChatRecordsExpanded;
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

  List<ContactSearchSuggestion> _buildContactSuggestions({
    required List<ChatContactSearchItemDto> contacts,
    required List<ConversationSearchItemView> allConversations,
  }) {
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
              : _resolveContactConversationId(
                  displayName: displayName,
                  allConversations: allConversations,
                ),
          avatarUrl: contact.avatarUrl,
          subtitle: contact.subtitle ?? '联系人',
        ),
      );
    }
    return suggestions;
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
        .take(SearchCoordinator._maxNetworkSuggestions)
        .toList(growable: false);
  }

  Future<void> _rememberQuery({required String query}) async {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final selectionFacet = _currentState.selection.toFacet();
    final historyScope = _scopeForSelection(_currentState.selection);
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
    ], _currentState.recentSearches);
    _setState(_currentState.copyWith(recentSearches: merged));
    await _localStore.save(merged);
    try {
      final remoteEntry = await _coordinatorRef
          .read(userProfileRepositoryProvider)
          .upsertRecentSearch(
            query: trimmedQuery,
            scope: historyScope,
            facet: selectionFacet,
          );
      final nextEntries = _mergeHistory(<RecentSearchEntryView>[
        remoteEntry,
      ], merged);
      if (!_isMounted) {
        return;
      }
      _setState(_currentState.copyWith(recentSearches: nextEntries));
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
}
