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
          .read(homepageQueryProvider)
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
        .map((hit) => hit.asChatContactItem)
        .whereType<ChatContactSearchItemDto>()
        .toList(growable: false);
    final conversationHits = responseHits
        .where((hit) => hit.objectType == SearchObjectType.chatConversation)
        .map((hit) => hit.asChatConversationItem)
        .whereType<ConversationSearchItemView>()
        .toList(growable: false);
    final messageHits = responseHits
        .where((hit) => hit.objectType == SearchObjectType.chatMessage)
        .map((hit) => hit.asChatMessageItem)
        .whereType<MessageSearchItemView>()
        .toList(growable: false);
    final circleSuggestions = includesCircles
        ? responseHits
              .where((hit) => hit.objectType == SearchObjectType.circleGroup)
              .map((hit) => hit.asCircleGroupItem)
              .whereType<CircleSearchItemView>()
              .toList(growable: false)
        : const <CircleSearchItemView>[];
    final locationSuggestions = responseHits
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.integrationLocationPoi ||
              hit.objectType == SearchObjectType.locationPlace,
        )
        .map(
          (hit) =>
              hit.asLocationPoiItem ??
              switch (hit.asLocationPlaceItem) {
                final item? => LocationPoiDto(
                  id: item.placeId,
                  name: item.name,
                  address: item.address,
                ),
                null => null,
              },
        )
        .whereType<LocationPoiDto>()
        .where((item) => item.name.trim().isNotEmpty)
        .toList(growable: false);
    final followedPeopleSuggestions = responseHits
        .where((hit) => hit.objectType == SearchObjectType.userProfile)
        .map((hit) => hit.asSocialRelationItem)
        .whereType<SocialRelationSearchItemView>()
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
            SearchObjectTarget.directChats => ChatText.searchChatDirect,
            SearchObjectTarget.groupChats => ChatText.searchChatGroup,
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
}
