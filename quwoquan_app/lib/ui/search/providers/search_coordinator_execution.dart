part of 'search_coordinator.dart';

extension SearchCoordinatorExecution on SearchCoordinator {
  Future<void> hydrateSearchInspiration() async {
    _setState(
      _currentState.copyWith(
        inspiration: _currentState.inspiration.copyWith(isLoading: true),
      ),
    );
    try {
      final circles = await _coordinatorRef
          .read(circleRepositoryProvider)
          .listCircles(limit: 9);
      final homepageRepository = _coordinatorRef.read(
        homepageRepositoryProvider,
      );
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
      final guessKeywords = _defaultGuessKeywords(batchIndex: 0);
      final hotLocations = locations
          .where((item) => item.title.trim().isNotEmpty)
          .take(6)
          .map(
            (item) => SearchInspirationCardView(
              id: item.id,
              title: item.title,
              subtitle:
                  '${(item.city ?? item.address ?? item.homepageType).trim()} · ${item.ratingCount > 0 ? '${item.ratingCount}条热度' : '热度上升'}',
              coverUrl: item.coverUrl,
              query: item.title,
            ),
          )
          .toList(growable: false);
      final hotCircles = circles
          .where((item) => item.name.trim().isNotEmpty)
          .take(6)
          .map(
            (item) => SearchInspirationCardView(
              id: item.id,
              title: item.name,
              subtitle:
                  '${_positiveCount(item.memberCount, item.weeklyActiveCount)}人 · ${item.description?.trim().isNotEmpty == true ? item.description!.trim() : '热门圈子'}',
              coverUrl: item.coverUrl,
              query: item.name,
            ),
          )
          .toList(growable: false);

      if (!_isMounted) {
        return;
      }
      _setState(
        _currentState.copyWith(
          inspiration: SearchInspirationState(
            guessKeywords: guessKeywords,
            guessBatchIndex: 0,
            hotCircles: hotCircles.isEmpty ? _defaultHotCircles() : hotCircles,
            hotLocations: hotLocations.isEmpty
                ? _defaultHotLocations()
                : hotLocations,
          ),
        ),
      );
    } catch (_) {
      if (!_isMounted) {
        return;
      }
      _setState(
        _currentState.copyWith(
          inspiration: _currentState.inspiration.copyWith(
            guessKeywords: _defaultGuessKeywords(batchIndex: 0),
            guessBatchIndex: 0,
            hotCircles: _defaultHotCircles(),
            hotLocations: _defaultHotLocations(),
            isLoading: false,
          ),
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

  void refreshGuessKeywords() {
    final nextIndex =
        (_currentState.inspiration.guessBatchIndex + 1) %
        _guessKeywordBatches.length;
    _setState(
      _currentState.copyWith(
        inspiration: _currentState.inspiration.copyWith(
          guessKeywords: _defaultGuessKeywords(batchIndex: nextIndex),
          guessBatchIndex: nextIndex,
        ),
      ),
    );
  }

  List<NetworkSearchSuggestion> _defaultGuessKeywords({
    required int batchIndex,
  }) {
    final seeds =
        _guessKeywordBatches[batchIndex % _guessKeywordBatches.length];
    return seeds
        .map((query) => NetworkSearchSuggestion(query: query, title: query))
        .toList(growable: false);
  }

  static const List<List<String>> _guessKeywordBatches = <List<String>>[
    <String>[
      '摄影',
      '厦门大学',
      '川西自驾',
      '鼓浪屿',
      '旅行',
      '富士X100V',
      '环岛路',
      '九寨沟',
      '武夷山',
      '大理',
    ],
    <String>[
      '毕业旅行',
      '环岛骑行',
      '富士相机',
      '大理旅行',
      '露营',
      '旅行攻略',
      '城市漫步',
      '咖啡地图',
      '日落机位',
      '周末徒步',
      '海边拍照',
      '小众博物馆',
    ],
  ];

  List<SearchInspirationCardView> _defaultHotCircles() {
    const seeds = <SearchInspirationCardView>[
      SearchInspirationCardView(
        id: 'circle_light_photo',
        title: '光影摄影社',
        subtitle: '128人 · 分享快门背后的故事',
        query: '光影摄影社',
      ),
      SearchInspirationCardView(
        id: 'circle_travel_notes',
        title: '旅行手账',
        subtitle: '1280人 · 热门圈子',
        query: '旅行手账',
      ),
      SearchInspirationCardView(
        id: 'circle_extreme_photo',
        title: '极简摄影俱乐部',
        subtitle: '2340人 · 热门圈子',
        query: '极简摄影俱乐部',
      ),
    ];
    return seeds;
  }

  List<SearchInspirationCardView> _defaultHotLocations() {
    const seeds = <SearchInspirationCardView>[
      SearchInspirationCardView(
        id: 'poi_xiamen_university',
        title: '厦门大学',
        subtitle: '高校 · 热度上升',
        query: '厦门大学',
      ),
      SearchInspirationCardView(
        id: 'poi_gulangyu',
        title: '鼓浪屿',
        subtitle: '景点 · 热度上升',
        query: '鼓浪屿',
      ),
      SearchInspirationCardView(
        id: 'poi_west_lake',
        title: '西湖',
        subtitle: '景点 · 热度上升',
        query: '西湖',
      ),
    ];
    return seeds;
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
          .read(userProfileRepositoryProvider)
          .deleteRecentSearch(entryId);
    } catch (_) {
      // Keep local-first delete even when remote cleanup fails.
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
          .read(userProfileRepositoryProvider)
          .clearRecentSearches();
    } catch (_) {
      // Keep local-first clear even when remote cleanup fails.
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
