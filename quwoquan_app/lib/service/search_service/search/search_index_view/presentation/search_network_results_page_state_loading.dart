part of 'search_network_results_page.dart';

extension _SearchNetworkResultsPageStateLoading
    on _SearchNetworkResultsPageState {
  Future<void> _loadResults() async {
    _recordSearchResultDwellIfNeeded();
    final token = ++_requestToken;
    final submittedAt = DateTime.now();
    final stopwatch = Stopwatch()..start();
    final trimmedQuery = _query.trim();
    final activeTabId = _activeTabId;
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'search_network_results',
          route: AppRoutePaths.globalSearch,
          surface: _activeTabId,
          phase: 'onlineLoading',
          copyKey: 'pageLoadingA11y',
          waitMode: _activeTabId == _SearchNetworkResultsPageState._tabXiaoqu
              ? 'long_task'
              : 'foreground',
        );
    _setMountedState(() {
      _isLoading = true;
      _isSlow = false;
      _errorSemantic = null;
      _degradeSignals = const <SearchDegradeSignal>[];
      if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
        _xiaoquResult = null;
      } else {
        _groupResults = const <SearchHit>[];
        _locationResults = const <SearchHit>[];
        _userResults = const <SearchHit>[];
        _contentResults = const <PostSearchItemView>[];
        _contentCloudMetaById = const <String, _ContentCloudMeta>{};
        _relatedTerms = const <String>[];
      }
    });
    late final int generation;
    try {
      if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
        generation = _waitController.start(
          mode: AppRequestWaitMode.longTask,
          showSlowHint: false,
        );
        // 空 query 不请求小趣搜（Remote 对空 query 抛结构化异常，且不再有
        // 本地合成的假摘要）；直接落空态。
        if (trimmedQuery.isEmpty) {
          if (!_isCurrentRequest(token, generation, activeTabId)) return;
          _setMountedState(() {
            _isLoading = false;
            _isSlow = false;
          });
          _waitController.complete(generation);
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'search_network_results',
                route: AppRoutePaths.globalSearch,
                surface: activeTabId,
                phase: 'emptySuccess',
                durationMs: stopwatch.elapsedMilliseconds,
                itemCount: 0,
                waitMode: 'long_task',
              );
          return;
        }
        final result = await ref
            .read(assistantSearchRunFacetProvider)
            .executeAssistantSearch(
              query: trimmedQuery,
              sessionClientRequestId: const Uuid().v4(),
              runClientRequestId: const Uuid().v4(),
            );
        if (!_isCurrentRequest(token, generation, activeTabId)) {
          return;
        }
        _setMountedState(() {
          _xiaoquResult = result;
          _isLoading = false;
          _isSlow = false;
        });
        _waitController.complete(generation);
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'search_network_results',
              route: AppRoutePaths.globalSearch,
              surface: _activeTabId,
              phase: 'onlineSuccess',
              durationMs: stopwatch.elapsedMilliseconds,
              itemCount: result.processes.fold<int>(
                0,
                (count, process) => count + process.acceptedReferences.length,
              ),
            );
        return;
      }

      final cancellation = CloudOperationCancellationSignal();
      generation = _waitController.start(
        mode: AppRequestWaitMode.foreground,
        cancellation: cancellation,
        onSlow: (_) {
          if (!_isCurrentRequest(token, generation, activeTabId)) return;
          _setMountedState(() => _isSlow = true);
        },
        onTimeout: (_) {
          if (!mounted ||
              token != _requestToken ||
              _activeTabId != activeTabId) {
            return;
          }
          final error = TimeoutException(
            'Canonical search exceeded the 6 second foreground budget.',
          );
          _setMountedState(() {
            _errorSemantic = _searchFailureSemantic(error);
            _isLoading = false;
            _isSlow = false;
          });
        },
        observer: (phase, durationMilliseconds) {
          if (phase == 'complete') return;
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'search_network_results',
                route: AppRoutePaths.globalSearch,
                surface: activeTabId,
                phase: phase,
                durationMs: durationMilliseconds,
                waitMode: 'foreground',
              );
        },
      );
      if (trimmedQuery.isEmpty) {
        if (!_isCurrentRequest(token, generation, activeTabId)) return;
        _setMountedState(() {
          _isLoading = false;
          _isSlow = false;
        });
        _waitController.complete(generation);
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'search_network_results',
              route: AppRoutePaths.globalSearch,
              surface: activeTabId,
              phase: 'emptySuccess',
              durationMs: stopwatch.elapsedMilliseconds,
              itemCount: 0,
              waitMode: 'foreground',
            );
        return;
      }

      // 正式结果页只调用 canonical POST /search 一次；云侧负责跨域 fan-out。
      final response = await ref
          .read(searchRepositoryProvider)
          .search(
            SearchRequest(
              query: trimmedQuery,
              mode: CanonicalSearchMode.result,
              objectTypes: _canonicalObjectTypes(activeTabId),
              contentTypes: _canonicalContentTypes(activeTabId),
              limit: 12,
            ),
            cancellation: cancellation,
            deadlineAt: DateTime.now().add(
              AppRequestWaitTimings.foregroundReadDeadline,
            ),
          );
      if (!_isCurrentRequest(token, generation, activeTabId)) {
        return;
      }
      _setMountedState(() {
        _groupResults = _groupHitsFromResponse(response);
        _locationResults = _locationHitsFromResponse(response);
        _userResults = _userHitsFromResponse(response);
        _contentResults = _contentItemsFromResponse(response);
        _relatedTerms = response.relatedTerms;
        _degradeSignals = response.degradeSignals;
        _searchRequestId = response.searchRequestId;
        _searchRankByObjectId = <String, int>{
          for (final hit in response.hits)
            if (hit.rankPosition != null) hit.objectId: hit.rankPosition!,
        };
        _isLoading = false;
        _isSlow = false;
      });
      _reportSearchImpression(response);
      _recordSearchResponseTelemetry(
        response: response,
        submittedAt: submittedAt,
        durationMs: stopwatch.elapsedMilliseconds,
        action: activeTabId,
      );
      _waitController.complete(generation);
      final itemCount =
          _contentResults.length +
          _locationResults.length +
          _groupResults.length +
          _userResults.length;
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'search_network_results',
            route: AppRoutePaths.globalSearch,
            surface: activeTabId,
            phase: response.degradeSignals.isNotEmpty
                ? 'partial'
                : (itemCount == 0 ? 'emptySuccess' : 'onlineSuccess'),
            durationMs: stopwatch.elapsedMilliseconds,
            itemCount: itemCount,
            waitMode: 'foreground',
          );
    } catch (error) {
      if (!mounted || token != _requestToken || _activeTabId != activeTabId) {
        return;
      }
      if (!_waitController.isCurrent(generation)) return;
      _setMountedState(() {
        _errorSemantic = _searchFailureSemantic(error);
        _isLoading = false;
        _isSlow = false;
      });
      _waitController.complete(generation);
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'search_network_results',
            route: AppRoutePaths.globalSearch,
            surface: _activeTabId,
            phase: 'blockingFailure',
            copyKey: 'searchUnavailableTitle',
            error: error,
            durationMs: stopwatch.elapsedMilliseconds,
            waitMode: activeTabId == _SearchNetworkResultsPageState._tabXiaoqu
                ? 'long_task'
                : 'foreground',
          );
    }
  }

  bool _isCurrentRequest(int token, int generation, String activeTabId) {
    return mounted &&
        token == _requestToken &&
        _activeTabId == activeTabId &&
        _waitController.isCurrent(generation);
  }

  Set<SearchObjectType> _canonicalObjectTypes(String activeTabId) {
    if (activeTabId == _SearchNetworkResultsPageState._tabIntersection) {
      return const <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.userProfile,
        SearchObjectType.entityHomepage,
        SearchObjectType.locationPlace,
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
      };
    }
    if (activeTabId == _SearchNetworkResultsPageState._tabAll) {
      return const <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.userProfile,
        SearchObjectType.entityHomepage,
        SearchObjectType.locationPlace,
      };
    }
    return const <SearchObjectType>{SearchObjectType.contentPost};
  }

  Set<SearchContentTypeFilter> _canonicalContentTypes(String activeTabId) {
    return switch (activeTabId) {
      _SearchNetworkResultsPageState._tabVideo =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.video},
      _SearchNetworkResultsPageState._tabImage =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.image},
      _SearchNetworkResultsPageState._tabArticle =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.article},
      _ => widget.launchContext.searchObjectSelection.normalized().contentTypes,
    };
  }

  UiErrorSemantic _searchFailureSemantic(Object error) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  List<PostSearchItemView> _contentItemsFromResponse(SearchResponse response) {
    final cloudMeta = <String, _ContentCloudMeta>{};
    final results = <PostSearchItemView>[];
    for (final hit in _hitsFromResponse(response)) {
      if (hit.objectType != SearchObjectType.contentPost) {
        continue;
      }
      final item = hit.asContentPostItem;
      if (item == null) {
        continue;
      }
      results.add(item);
      final meta = _ContentCloudMeta(
        rankPosition: hit.rankPosition,
        coverWidth: hit.coverWidth,
        coverHeight: hit.coverHeight,
        rankReasons: hit.rankReasons,
      );
      if (item.postId.isNotEmpty && meta.hasCloudSignal) {
        cloudMeta[item.postId] = meta;
      }
    }
    // R-001：命中携带云侧 rankPosition 时，按云侧排序而非端侧 publishedAt 兜底排序。
    final hasCloudRank = results.any(
      (item) => cloudMeta[item.postId]?.rankPosition != null,
    );
    if (hasCloudRank) {
      results.sort((left, right) {
        final leftRank = cloudMeta[left.postId]?.rankPosition;
        final rightRank = cloudMeta[right.postId]?.rankPosition;
        if (leftRank == null && rightRank == null) {
          return 0;
        }
        if (leftRank == null) {
          return 1;
        }
        if (rightRank == null) {
          return -1;
        }
        return leftRank.compareTo(rightRank);
      });
    } else {
      results.sort((left, right) {
        final leftTime = left.publishedAt;
        final rightTime = right.publishedAt;
        if (leftTime == null && rightTime == null) {
          return 0;
        }
        if (leftTime == null) {
          return 1;
        }
        if (rightTime == null) {
          return -1;
        }
        return rightTime.compareTo(leftTime);
      });
    }
    final sorted = results.take(12).toList(growable: false);
    _contentCloudMetaById = cloudMeta;
    return sorted;
  }
}
