part of 'search_coordinator.dart';

extension SearchCoordinatorExecution on SearchCoordinator {
  Future<void> hydrateSearchInspiration() async {
    _setState(
      _currentState.copyWith(
        inspiration: _currentState.inspiration.copyWith(isLoading: true),
      ),
    );
    var hotQueryPool = const <NetworkSearchSuggestion>[];
    var discoverCircles = const <SearchInspirationCardView>[];
    var discoverLocations = const <SearchInspirationCardView>[];
    await Future.wait<void>(<Future<void>>[
      _loadHotQuerySuggestions().then((value) => hotQueryPool = value),
      _loadDiscoverCircles().then((value) => discoverCircles = value),
      _loadDiscoverLocations().then((value) => discoverLocations = value),
    ]);
    if (!_isMounted) {
      return;
    }
    _hotQueryPool = hotQueryPool;
    _setState(
      _currentState.copyWith(
        inspiration: SearchInspirationState(
          guessKeywords: _guessKeywordsForBatch(0),
          guessBatchIndex: 0,
          discoverCircles: discoverCircles,
          discoverLocations: discoverLocations,
        ),
      ),
    );
  }

  Future<List<NetworkSearchSuggestion>> _loadHotQuerySuggestions() async {
    try {
      final slice = await _coordinatorRef
          .read(searchHotQueryReaderProvider)
          .listHotQueries(ListHotQueriesQuery(limit: 20));
      return slice.items
          .where((item) => item.query.trim().isNotEmpty)
          .map(
            (item) =>
                NetworkSearchSuggestion(query: item.query, title: item.query),
          )
          .toList(growable: false);
    } on Object catch (error) {
      _recordInspirationFailure('hot_queries', error);
      return const <NetworkSearchSuggestion>[];
    }
  }

  Future<List<SearchInspirationCardView>> _loadDiscoverCircles() async {
    try {
      final circles =
          (await _coordinatorRef
                  .read(circlesListQueryProvider)
                  .list(CircleListQuery(limit: 9)))
              .items;
      return circles
          .where((item) => item.name.trim().isNotEmpty)
          .take(6)
          .map(
            (item) => SearchInspirationCardView(
              id: item.circleId,
              title: item.name,
              subtitle: UITextConstants.searchCircleInspirationSubtitle(
                _positiveCount(item.memberCount, item.weeklyActiveCount),
                item.description?.trim().isNotEmpty == true
                    ? item.description!.trim()
                    : UITextConstants.searchHomeDiscoverCirclesTitle,
              ),
              coverUrl: item.coverUrl,
              query: item.name,
            ),
          )
          .toList(growable: false);
    } on Object catch (error) {
      _recordInspirationFailure('discover_circles', error);
      return const <SearchInspirationCardView>[];
    }
  }

  Future<List<SearchInspirationCardView>> _loadDiscoverLocations() async {
    try {
      final locations = await _coordinatorRef
          .read(homepageQueryProvider)
          .searchHomepages(query: '', limit: 30);
      return locations
          .where(
            (item) =>
                item.title.trim().isNotEmpty &&
                SearchCoordinator._locationHomepageTypes.contains(
                  item.homepageType.trim(),
                ),
          )
          .take(6)
          .map(
            (item) => SearchInspirationCardView(
              id: item.id,
              title: item.title,
              subtitle: UITextConstants.searchLocationDiscoverySubtitle(
                (item.city ?? item.address ?? item.homepageType).trim(),
                item.ratingCount,
              ),
              coverUrl: item.coverUrl,
              query: item.title,
            ),
          )
          .toList(growable: false);
    } on Object catch (error) {
      _recordInspirationFailure('discover_locations', error);
      return const <SearchInspirationCardView>[];
    }
  }

  void _recordInspirationFailure(String source, Object error) {
    _coordinatorRef
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'global_search',
          route: 'globalSearch',
          surface: 'globalSearchLanding',
          phase: 'inspiration_${source}_failed',
          waitMode: 'background',
          error: error,
        );
    if (kDebugMode) {
      debugPrint('search inspiration $source degraded to empty: $error');
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

  void refreshGuessKeywords() {
    if (_hotQueryPool.isEmpty) {
      return;
    }
    final batchCount =
        (_hotQueryPool.length / SearchCoordinator._guessKeywordBatchSize)
            .ceil();
    final nextIndex =
        (_currentState.inspiration.guessBatchIndex + 1) % batchCount;
    _setState(
      _currentState.copyWith(
        inspiration: _currentState.inspiration.copyWith(
          guessKeywords: _guessKeywordsForBatch(nextIndex),
          guessBatchIndex: nextIndex,
        ),
      ),
    );
  }

  List<NetworkSearchSuggestion> _guessKeywordsForBatch(int batchIndex) {
    if (_hotQueryPool.isEmpty) {
      return const <NetworkSearchSuggestion>[];
    }
    final start = batchIndex * SearchCoordinator._guessKeywordBatchSize;
    final end = math.min(
      start + SearchCoordinator._guessKeywordBatchSize,
      _hotQueryPool.length,
    );
    return _hotQueryPool.sublist(start, end);
  }

  Future<void> useRecentSearch(RecentSearchEntryView entry) async {
    final facetSelection = SearchObjectSelection.fromFacet(entry.facet);
    final selection = facetSelection.isEmpty
        ? SearchObjectSelection.fromSearchScope(entry.scope)
        : facetSelection;
    _setState(
      _currentState.copyWith(
        query: entry.query,
        scope: entry.scope,
        selection: selection,
        launchContext: _currentState.launchContext.copyWith(
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
    return _rememberQuery(query: query ?? _currentState.query);
  }

  Future<void> removeRecentSearch(String entryId) async {
    final nextEntries = _currentState.recentSearches
        .where((entry) => entry.entryId != entryId)
        .toList(growable: false);
    _setState(
      _currentState.copyWith(
        recentSearches: nextEntries,
        isManagingHistory: nextEntries.isEmpty
            ? false
            : _currentState.isManagingHistory,
        isHistoryExpanded: nextEntries.isEmpty
            ? false
            : _currentState.isHistoryExpanded,
      ),
    );
    await _localStore.save(nextEntries);
    try {
      await _coordinatorRef
          .read(recentSearchCommandWriterProvider)
          .deleteRecentSearch(DeleteRecentSearchCommand(entryId: entryId));
    } on Object catch (error) {
      // Local-first delete stays; remote cleanup failure is logged, not hidden.
      if (kDebugMode) {
        debugPrint('recent search remote delete degraded: $error');
      }
    }
  }

  Future<void> clearRecentSearches() async {
    _setState(
      _currentState.copyWith(
        recentSearches: const <RecentSearchEntryView>[],
        isManagingHistory: false,
        isHistoryExpanded: false,
      ),
    );
    await _localStore.clear();
    try {
      await _coordinatorRef
          .read(recentSearchCommandWriterProvider)
          .clearRecentSearches(ClearRecentSearchesCommand());
    } on Object catch (error) {
      // Local-first clear stays; remote cleanup failure is logged, not hidden.
      if (kDebugMode) {
        debugPrint('recent search remote clear degraded: $error');
      }
    }
  }

  Future<void> _performSearch() async {
    final query = _currentState.query.trim();
    if (query.isEmpty) {
      _setState(
        _currentState.copyWith(
          isLoading: false,
          isNetworkLoading: false,
          isSlow: false,
          isPartial: false,
          failure: () => null,
          suggestionSections: const <SearchSuggestionSection>[],
        ),
      );
      return;
    }
    _waitController.cancel();
    final token = ++_searchRequestToken;
    final selection = _currentState.selection.normalized();
    final cancellation = CloudOperationCancellationSignal();
    late final int generation;
    generation = _waitController.start(
      mode: AppRequestWaitMode.foreground,
      cancellation: cancellation,
      onSlow: (_) {
        if (!_isCurrentSearch(token, generation) ||
            _hasBrowsableLocalSuggestions(_currentState.suggestionSections)) {
          return;
        }
        _setState(_currentState.copyWith(isSlow: true));
      },
      onTimeout: (_) {
        if (!_isMounted || token != _searchRequestToken) {
          return;
        }
        final timeout = TimeoutException(
          'Search foreground read exceeded the 6 second budget.',
        );
        _setState(
          _currentState.copyWith(
            isLoading: false,
            isNetworkLoading: false,
            isSlow: false,
            isPartial: _currentState.suggestionSections.isNotEmpty,
            failure: () => timeout,
          ),
        );
      },
      observer: (phase, durationMilliseconds) {
        if (phase == 'complete') return;
        _coordinatorRef
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'global_search',
              phase: phase,
              route: 'globalSearch',
              surface: 'globalSearch',
              durationMs: durationMilliseconds,
              waitMode: 'foreground',
            );
      },
    );
    _setState(
      _currentState.copyWith(
        isLoading: true,
        isNetworkLoading: _allowsHomepageSearch(selection),
        isSlow: false,
        isPartial: false,
        failure: () => null,
      ),
    );

    final outcomes = <_SuggestionDomainOutcome>[];
    final localFuture =
        _settleLocalSuggestions(
          query: query,
          selection: selection,
          token: token,
          generation: generation,
          cancellation: cancellation,
        ).then<void>((outcome) {
          outcomes.add(outcome);
        });
    final homepageFuture = _allowsHomepageSearch(selection)
        ? _settleHomepageSuggestions(
            query: query,
            token: token,
            generation: generation,
            cancellation: cancellation,
          ).then<void>((outcome) {
            outcomes.add(outcome);
          })
        : Future<void>.value();

    await Future.wait<void>(<Future<void>>[localFuture, homepageFuture]);
    if (!_isCurrentSearch(token, generation)) {
      return;
    }
    _waitController.complete(generation);
    final failed = outcomes
        .where((item) => item.failed)
        .toList(growable: false);
    final allFailed = outcomes.isNotEmpty && failed.length == outcomes.length;
    final failure = failed.isEmpty ? null : failed.first.error;
    if (failed.isNotEmpty && !allFailed) {
      _coordinatorRef
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'global_search',
            phase: 'partial',
            route: 'globalSearch',
            surface: 'globalSearch',
            waitMode: 'foreground',
            error: failure,
          );
    }
    _setState(
      _currentState.copyWith(
        isLoading: false,
        isNetworkLoading: false,
        isSlow: false,
        isPartial: failed.isNotEmpty && !allFailed,
        failure: () => failed.isEmpty ? null : failure,
      ),
    );
  }
}
