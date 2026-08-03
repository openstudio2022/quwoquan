part of 'search_coordinator.dart';

extension SearchCoordinatorSuggestionBuilders on SearchCoordinator {
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
          userHandle: contact.userHandle.trim(),
          displayName: displayName,
          conversationId: directConversationId.isNotEmpty
              ? directConversationId
              : _resolveContactConversationId(
                  displayName: displayName,
                  allConversations: allConversations,
                ),
          avatarUrl: contact.avatarUrl,
          subtitle: contact.subtitle ?? ChatText.searchContactFallback,
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
    return '';
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
        subtitle: SearchText.searchAllResults,
        initialTabId: 'all',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: UITextConstants.searchQueryIntersection(query),
        subtitle: SearchText.searchBestConnections,
        initialTabId: 'intersection',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: UITextConstants.searchQueryImages(query),
        subtitle: SearchText.searchOnlyImages,
        initialTabId: 'image',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: UITextConstants.searchQueryVideos(query),
        subtitle: SearchText.searchOnlyVideos,
        initialTabId: 'video',
      ),
      NetworkSearchSuggestion(
        query: query,
        title: UITextConstants.searchQueryArticles(query),
        subtitle: SearchText.searchOnlyArticles,
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
    final store = _localStore;
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    _recentHistoryMutationRevision += 1;
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
    final historyKey = _historyKeyForEntry(localEntry);
    _pendingRecentDeleteKeys.remove(historyKey);
    _pendingRecentUpsertKeys.add(historyKey);
    final upsertToken = ++_recentUpsertSequence;
    _recentUpsertTokens[historyKey] = upsertToken;
    await _saveRecentHistory(merged, store: store);
    if (!_isMounted || !identical(store, _localStore)) {
      return;
    }
    if (_pendingRecentClear) {
      return;
    }
    try {
      final remoteContractEntry = await _coordinatorRef
          .read(recentSearchCommandWriterProvider)
          .upsertRecentSearch(
            UpsertRecentSearchCommand(
              query: trimmedQuery,
              scope: historyScope.wireValue,
              facet: selectionFacet,
            ),
          );
      final remoteEntry = RecentSearchEntryView.fromWire(remoteContractEntry);
      if (!_isMounted || !identical(store, _localStore)) {
        return;
      }
      final currentIntentContainsEntry = _currentState.recentSearches.any(
        (entry) => _historyKeyForEntry(entry) == historyKey,
      );
      if (_recentUpsertTokens[historyKey] != upsertToken ||
          _pendingRecentDeleteKeys.contains(historyKey) ||
          !currentIntentContainsEntry) {
        if (!currentIntentContainsEntry) {
          _pendingRecentDeleteKeys.add(historyKey);
          final deleted = await _deleteCanonicalRecentSearch(
            remoteEntry,
            operation: 'remote_delete_after_obsolete_upsert',
          );
          if (deleted) {
            _pendingRecentDeleteKeys.remove(historyKey);
          }
          await _saveRecentHistory(_currentState.recentSearches, store: store);
        }
        return;
      }
      final nextEntries = _replaceHistoryEntryWithCanonical(
        _currentState.recentSearches,
        remoteEntry,
      );
      _recentUpsertTokens.remove(historyKey);
      _pendingRecentUpsertKeys.remove(historyKey);
      _setState(_currentState.copyWith(recentSearches: nextEntries));
      await _saveRecentHistory(nextEntries, store: store);
    } on Object catch (error) {
      // Local-first history stays available while remote sync degrades.
      _recordRecentHistoryFailure(operation: 'remote_upsert', error: error);
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
    return values
        .take(SearchCoordinator._recentSearchMaxEntries)
        .toList(growable: false);
  }

  List<RecentSearchEntryView> _replaceHistoryEntryWithCanonical(
    List<RecentSearchEntryView> entries,
    RecentSearchEntryView canonicalEntry,
  ) {
    final canonicalKey = _historyKeyForEntry(canonicalEntry);
    return _mergeHistory(
      <RecentSearchEntryView>[canonicalEntry],
      entries
          .where((entry) => _historyKeyForEntry(entry) != canonicalKey)
          .toList(growable: false),
    );
  }
}
