part of 'discovery_feed_provider.dart';

abstract class _DiscoveryFeedMapLoadingCore
    extends Notifier<Map<String, AsyncValue<DiscoveryFeedState>>> {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    ref.listen(homeChannelsProvider, (previous, next) {
      if (previous == null) {
        return;
      }
      final nextHomeChannelIds = next
          .map((channel) => channel.id.trim())
          .where((channelId) => channelId.isNotEmpty)
          .toSet();
      final removedHomeChannelIds = previous
          .map((channel) => channel.id.trim())
          .where(
            (channelId) =>
                channelId.isNotEmpty && !nextHomeChannelIds.contains(channelId),
          )
          .toSet();
      _reclaimRemovedHomeChannels(removedHomeChannelIds);
    });
    ref.listen<int>(contentPublicationEpochProvider, (previous, next) {
      if (previous == null || previous == next) {
        return;
      }
      final loadedChannels = state.keys.toList(growable: false);
      for (final channelId in loadedChannels) {
        unawaited(load(channelId, force: true));
      }
    });
    ref.onDispose(() {
      for (final controller in _refreshWaitControllers.values) {
        controller.dispose();
      }
      for (final controller in _appendWaitControllers.values) {
        controller.dispose();
      }
      for (final controller in _prependWaitControllers.values) {
        controller.dispose();
      }
      _refreshWaitControllers.clear();
      _appendWaitControllers.clear();
      _prependWaitControllers.clear();
      _residentPageWindows.clear();
    });
    return {};
  }

  final Map<String, AppRequestWaitController> _refreshWaitControllers =
      <String, AppRequestWaitController>{};
  final Map<String, AppRequestWaitController> _appendWaitControllers =
      <String, AppRequestWaitController>{};
  final Map<String, AppRequestWaitController> _prependWaitControllers =
      <String, AppRequestWaitController>{};
  final Map<String, DiscoveryFeedResidentPageWindow> _residentPageWindows =
      <String, DiscoveryFeedResidentPageWindow>{};

  /// 只回收旧首页配置中消失的频道；不得扫描 [state] 删除非首页 discovery tab。
  void _reclaimRemovedHomeChannels(Set<String> removedHomeChannelIds) {
    if (removedHomeChannelIds.isEmpty) {
      return;
    }
    for (final channelId in removedHomeChannelIds) {
      _refreshWaitControllers.remove(channelId)?.dispose();
      _appendWaitControllers.remove(channelId)?.dispose();
      _prependWaitControllers.remove(channelId)?.dispose();
      _residentPageWindows.remove(channelId);
    }
    if (!removedHomeChannelIds.any(state.containsKey)) {
      return;
    }
    final retained = Map<String, AsyncValue<DiscoveryFeedState>>.from(
      state,
    )..removeWhere((channelId, _) => removedHomeChannelIds.contains(channelId));
    state = retained;
  }

  /// 解析取数查询：首页频道以 [homeChannelsProvider]（端默认 + 远程覆盖）的 feed_query 为真相源；
  /// 非首页频道（发现 tab photo/video/...）回退 [toDiscoveryFeedQuery]。
  ///
  /// feed_query.channel 是频道推荐主链路标识（B1 收口）：命中即以 channelId 请求
  /// 推荐引擎，identity/type 不参与。仅当 feed_query 只声明 category（旧浏览流
  /// 语义，运营远程覆盖兼容窗口）时才透传 identity/type。
  DiscoveryFeedQuery _resolveQuery(String channelId) {
    for (final channel in ref.read(homeChannelsProvider)) {
      if (channel.id != channelId) continue;
      final routedChannel = channel.feedQuery['channel'];
      if (routedChannel != null && routedChannel.isNotEmpty) {
        return (
          category: routedChannel,
          channel: routedChannel,
          identity: null,
          type: null,
        );
      }
      final category = channel.feedQuery['category'];
      if (category != null && category.isNotEmpty) {
        return (
          category: category,
          channel: null,
          identity: channel.feedQuery['identity'],
          type: channel.feedQuery['type'],
        );
      }
    }
    return toDiscoveryFeedQuery(channelId);
  }

  DiscoveryFeedResidentPageWindow _createInitialResidentPageWindow(
    DiscoveryFeedPage page,
  ) {
    return DiscoveryFeedResidentPageWindow.initial(
      DiscoveryFeedResidentPage.fromEnvelope(incomingCursor: null, page: page),
    );
  }

  DiscoveryFeedState _withResidentPageWindow(
    DiscoveryFeedState value,
    DiscoveryFeedResidentPageWindow window,
  ) {
    return value.copyWith(
      items: window.visibleItems,
      objectCards: window.visibleObjectCards,
      nextCursor: window.nextCursor,
      canRestorePreviousPage: window.canRestorePreviousPage,
      hasBufferedNextPage: window.canRestoreNextPage,
      residentPageCount: window.residentPages.length,
      retainedPageCount: window.retainedPageCount,
    );
  }

  List<String> _boundedSeenItemIds(
    Iterable<String> current,
    Iterable<String> appended,
  ) {
    final ids = <String>{};
    for (final rawId in <String>[...current, ...appended]) {
      final postId = rawId.trim();
      if (postId.isEmpty) {
        continue;
      }
      // 重复出现视为最近再次观察，移动到 LRU 尾部。
      ids.remove(postId);
      ids.add(postId);
      while (ids.length > homeFeedSeenItemLimit) {
        ids.remove(ids.first);
      }
    }
    return List<String>.unmodifiable(ids);
  }

  ({
    int leadingPages,
    int residentPages,
    int trailingPages,
    int retainedPages,
    int retainedItems,
  })?
  residentPageWindowDiagnostics(String channelId) {
    final window = _residentPageWindows[channelId.trim()];
    if (window == null) {
      return null;
    }
    return (
      leadingPages: window.leadingPages.length,
      residentPages: window.residentPages.length,
      trailingPages: window.trailingPages.length,
      retainedPages: window.retainedPageCount,
      retainedItems: window.retainedItemCount,
    );
  }

  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async {
    final currentValue = state[channelId]?.value;
    if (!force && currentValue != null && currentValue.items.isNotEmpty) {
      return DiscoveryFeedLoadResult(
        terminal: currentValue.staleDataError == null
            ? DiscoveryFeedLoadTerminal.content
            : DiscoveryFeedLoadTerminal.retainedContent,
        generation: _refreshWaitControllers[channelId]?.generation ?? 0,
        failure: currentValue.staleDataError,
      );
    }
    final repo = ref.read(contentDiscoveryFeedQueryProvider);
    final query = _resolveQuery(channelId);
    final feedSession = ref.read(feedSessionProvider.notifier);
    final sessionId = feedSession.sessionId;
    // 刷新拥有更新的窗口语义：先终止旧分页，再开始新的
    // refresh generation。两者使用独立 controller，分页不能反向取消刷新。
    _appendWaitControllers[channelId]?.cancel();
    _prependWaitControllers[channelId]?.cancel();
    final controller = _refreshWaitControllers.putIfAbsent(
      channelId,
      AppRequestWaitController.new,
    );
    final cancellation = CloudOperationCancellationSignal();
    late final int generation;
    generation = controller.start(
      mode: AppRequestWaitMode.foreground,
      cancellation: cancellation,
      onSlow: (_) {
        if (!controller.isCurrent(generation)) return;
        final value = state[channelId]?.value;
        if (value == null || value.items.isNotEmpty) return;
        state = {...state, channelId: AsyncData(value.copyWith(isSlow: true))};
      },
      onTimeout: (_) {
        final value = state[channelId]?.value;
        if (value == null) return;
        final error = _normalizeDiscoveryFeedError(
          TimeoutException(
            'Home foreground read exceeded the 6 second budget.',
          ),
        );
        state = {
          ...state,
          channelId: AsyncData(
            value.copyWith(
              isLoading: false,
              isRefreshing: false,
              isAppending: false,
              isSlow: false,
              blockingError: value.items.isEmpty ? error : null,
              staleDataError: value.items.isNotEmpty ? error : null,
            ),
          ),
        };
      },
      observer: (phase, durationMilliseconds) {
        if (phase == 'complete') return;
        _recordPageState(
          channelId,
          phase: phase,
          source: 'online',
          hasCache: currentValue?.items.isNotEmpty ?? false,
          itemCount: currentValue?.items.length,
          durationMs: durationMilliseconds,
        );
      },
    );
    state = {
      ...state,
      channelId: AsyncData(
        (currentValue ?? const DiscoveryFeedState()).copyWith(
          isLoading: currentValue?.items.isEmpty ?? true,
          isRefreshing: true,
          isAppending: false,
          isSlow: false,
          blockingError: null,
          staleDataError: null,
          appendError: null,
        ),
      ),
    };
    _recordPageState(
      channelId,
      phase: 'onlineLoading',
      source: 'online',
      hasCache: currentValue?.items.isNotEmpty ?? false,
      itemCount: currentValue?.items.length,
    );
    try {
      // 首刷不传 feedRequestId：由服务端权威生成并随 envelope 下发。
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        channelId: query.channel,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: null,
        sessionId: sessionId,
        feedRequestId: null,
        cancellation: cancellation,
        deadlineAt: DateTime.now().add(
          AppRequestWaitTimings.foregroundReadDeadline,
        ),
      );
      if (!controller.isCurrent(generation)) {
        return _terminalLoadResult(channelId, controller, generation);
      }
      final revalidation = page.revalidation;
      if (revalidation != null) {
        _applyInitialPage(
          channelId,
          page,
          keepRefreshing: true,
          isStaleSnapshot: true,
        );
        final revalidatedPage = await revalidation;
        if (!controller.isCurrent(generation)) {
          return _terminalLoadResult(channelId, controller, generation);
        }
        _applyInitialPage(
          channelId,
          revalidatedPage,
          keepRefreshing: false,
          isStaleSnapshot: false,
        );
      } else {
        _applyInitialPage(
          channelId,
          page,
          keepRefreshing: false,
          isStaleSnapshot: false,
        );
      }
      return _terminalLoadResult(channelId, controller, generation);
    } catch (e, st) {
      if (!controller.isCurrent(generation)) {
        return _terminalLoadResult(channelId, controller, generation);
      }
      final error = _normalizeDiscoveryFeedError(e);
      final latestValue = state[channelId]?.value ?? currentValue;
      if (error.runtimeFailure.kind == RuntimeFailureKind.cancelled) {
        state = {
          ...state,
          channelId: AsyncData(
            (latestValue ?? const DiscoveryFeedState()).copyWith(
              isLoading: false,
              isRefreshing: false,
              isAppending: false,
              isSlow: false,
              blockingError: null,
            ),
          ),
        };
        return _terminalLoadResult(channelId, controller, generation);
      }
      developer.log(
        'load error: $error',
        name: 'DiscoveryFeed',
        error: error,
        stackTrace: st,
      );
      if (latestValue != null && latestValue.items.isNotEmpty) {
        state = {
          ...state,
          channelId: AsyncData(
            latestValue.copyWith(
              isLoading: false,
              isRefreshing: false,
              isAppending: false,
              isSlow: false,
              staleDataError: error,
              blockingError: null,
            ),
          ),
        };
        _recordPageState(
          channelId,
          phase: 'cacheFallback',
          source: 'retained',
          error: error,
          copyKey: 'homeCacheFallback',
          hasCache: true,
          itemCount: latestValue.items.length,
          requestId: latestValue.feedRequestId,
        );
        return DiscoveryFeedLoadResult(
          terminal: DiscoveryFeedLoadTerminal.retainedContent,
          generation: generation,
          failure: error,
        );
      }
      state = {
        ...state,
        channelId: AsyncData(
          DiscoveryFeedState(
            blockingError: error,
            isLoading: false,
            isRefreshing: false,
            isAppending: false,
          ),
        ),
      };
      _residentPageWindows.remove(channelId);
      _recordPageState(
        channelId,
        phase: 'blockingFailure',
        source: 'online',
        error: error,
        hasCache: false,
        itemCount: 0,
      );
      return DiscoveryFeedLoadResult(
        terminal: DiscoveryFeedLoadTerminal.stillBlocked,
        generation: generation,
        failure: error,
      );
    } finally {
      controller.complete(generation);
    }
  }

  DiscoveryFeedLoadResult _terminalLoadResult(
    String channelId,
    AppRequestWaitController controller,
    int generation,
  ) {
    if (controller.generation != generation) {
      return DiscoveryFeedLoadResult(
        terminal: controller.isDisposed
            ? DiscoveryFeedLoadTerminal.cancelled
            : DiscoveryFeedLoadTerminal.superseded,
        generation: generation,
      );
    }
    final value = state[channelId]?.value;
    if (value?.blockingError != null) {
      return DiscoveryFeedLoadResult(
        terminal: DiscoveryFeedLoadTerminal.stillBlocked,
        generation: generation,
        failure: value!.blockingError,
      );
    }
    if (value != null && value.items.isNotEmpty) {
      return DiscoveryFeedLoadResult(
        terminal: value.staleDataError == null
            ? DiscoveryFeedLoadTerminal.content
            : DiscoveryFeedLoadTerminal.retainedContent,
        generation: generation,
        failure: value.staleDataError,
      );
    }
    if (value?.emptyReason != null) {
      return DiscoveryFeedLoadResult(
        terminal: DiscoveryFeedLoadTerminal.canonicalEmpty,
        generation: generation,
      );
    }
    return DiscoveryFeedLoadResult(
      terminal: DiscoveryFeedLoadTerminal.cancelled,
      generation: generation,
    );
  }

  void _applyInitialPage(
    String channelId,
    DiscoveryFeedPage page, {
    required bool keepRefreshing,
    required bool isStaleSnapshot,
  }) {
    final retainedValue = state[channelId]?.value;
    final hasRetainedItems = retainedValue?.items.isNotEmpty ?? false;
    final hasInitialPageProtocolViolation =
        !isStaleSnapshot &&
        page.cacheFallbackError == null &&
        ((page.items.isEmpty &&
                !_isCanonicalInitialEmptyPage(
                  channelId,
                  page,
                  releaseRequirement: ref.read(
                    contentReleaseRequirementProvider,
                  ),
                )) ||
            (page.items.isNotEmpty &&
                (page.outcome != ContentFeedOutcome.content ||
                    page.emptyReason != null)));
    if (hasInitialPageProtocolViolation) {
      final error = discoveryFeedInitialPageProtocolFailure(channelId);
      developer.log(
        'Initial discovery feed page contained no displayable items.',
        name: 'DiscoveryFeed',
        error: error,
      );
      state = {
        ...state,
        channelId: AsyncData(
          hasRetainedItems
              ? retainedValue!.copyWith(
                  isLoading: false,
                  isRefreshing: false,
                  isAppending: false,
                  isSlow: false,
                  blockingError: null,
                  staleDataError: error,
                  appendError: null,
                )
              : DiscoveryFeedState(
                  blockingError: error,
                  isLoading: false,
                  isRefreshing: false,
                  isAppending: false,
                  isSlow: false,
                ),
        ),
      };
      if (!hasRetainedItems) {
        _residentPageWindows.remove(channelId);
      }
      _recordPageState(
        channelId,
        phase: hasRetainedItems ? 'cacheFallback' : 'blockingFailure',
        source: hasRetainedItems ? 'retained' : 'localConsistency',
        error: error,
        copyKey: hasRetainedItems ? 'homeCacheFallback' : null,
        hasCache: hasRetainedItems,
        itemCount: hasRetainedItems ? retainedValue!.items.length : 0,
        requestId: hasRetainedItems ? retainedValue!.feedRequestId : null,
      );
      return;
    }
    // 先验证单页内存预算；超限必须在任何归因/互动副作用前 fail-closed。
    _requireCanonicalPolicyDigest(page.policyDigest);
    final residentWindow = _createInitialResidentPageWindow(page);
    // 采纳服务端下发的归因 id，使后续曝光/点击/打开复用同一 feedRequestId。
    ref
        .read(feedSessionProvider.notifier)
        .adoptServerFeedRequestId(page.feedRequestId);
    ref
        .read(postInteractionStateProvider.notifier)
        .applyConfirmedPosts(
          page.items,
          pendingLikePostIds: ref.read(pendingLikeSyncPostIdsProvider),
        );
    final seen = _boundedSeenItemIds(
      const <String>[],
      residentWindow.visibleItems.map((item) => item.id),
    );
    final fallbackError = page.cacheFallbackError == null
        ? null
        : _normalizeDiscoveryFeedError(page.cacheFallbackError!);
    final hasDisplayableCache = page.items.isNotEmpty;
    _residentPageWindows[channelId] = residentWindow;
    state = {
      ...state,
      channelId: AsyncData(
        DiscoveryFeedState(
          items: residentWindow.visibleItems,
          objectCards: residentWindow.visibleObjectCards,
          seenItemIds: seen,
          nextCursor: residentWindow.nextCursor,
          feedRequestId: page.feedRequestId,
          policyDigest: page.policyDigest,
          emptyReason: page.emptyReason,
          canRestorePreviousPage: residentWindow.canRestorePreviousPage,
          hasBufferedNextPage: residentWindow.canRestoreNextPage,
          residentPageCount: residentWindow.residentPages.length,
          retainedPageCount: residentWindow.retainedPageCount,
          blockingError: fallbackError != null && !hasDisplayableCache
              ? fallbackError
              : null,
          staleDataError: fallbackError != null && hasDisplayableCache
              ? fallbackError
              : null,
          isLoading: keepRefreshing && !hasDisplayableCache,
          isRefreshing: keepRefreshing,
          isAppending: false,
          isSlow: false,
        ),
      ),
    };
    final phase = isStaleSnapshot
        ? 'cacheFallback'
        : fallbackError == null
        ? 'onlineSuccess'
        : hasDisplayableCache
        ? 'cacheFallback'
        : 'blockingFailure';
    _recordPageState(
      channelId,
      phase: phase,
      source: isStaleSnapshot || (fallbackError != null && hasDisplayableCache)
          ? 'cache'
          : 'online',
      error: fallbackError,
      copyKey: fallbackError != null && hasDisplayableCache
          ? 'homeCacheFallback'
          : null,
      hasCache:
          isStaleSnapshot || (fallbackError != null && hasDisplayableCache),
      cacheAgeMs: page.cacheAgeMs,
      itemCount: page.items.length,
      requestId: page.feedRequestId,
    );
  }

  void _recordPageState(
    String channelId, {
    required String phase,
    required String source,
    Object? error,
    String? copyKey,
    bool? hasCache,
    int? cacheAgeMs,
    int? itemCount,
    String? requestId,
    int? durationMs,
  }) {
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'home',
          route: '/home',
          surface: channelId,
          phase: phase,
          source: source,
          error: error,
          copyKey: copyKey,
          hasCache: hasCache,
          cacheAgeMs: cacheAgeMs,
          itemCount: itemCount,
          requestId: requestId,
          durationMs: durationMs,
          waitMode: 'foreground',
        );
  }

  void _recordAppend(
    String channelId, {
    required String result,
    required bool cursorPresent,
    required bool hasMore,
    int? itemCountBefore,
    int? itemCountAfter,
    Object? error,
    String? copyKey,
  }) {
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordAppend(
          pageName: 'home:$channelId',
          result: result,
          cursorPresent: cursorPresent,
          hasMore: hasMore,
          itemCountBefore: itemCountBefore,
          itemCountAfter: itemCountAfter,
          error: error,
          copyKey: copyKey,
        );
  }

  void _recordPreviousPage(
    String channelId, {
    required String result,
    required int itemCountBefore,
    required int itemCountAfter,
    Object? error,
  }) {
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordAppend(
          pageName: 'home:$channelId:previous',
          result: result,
          cursorPresent: true,
          hasMore:
              _residentPageWindows[channelId]?.canRestorePreviousPage ?? false,
          itemCountBefore: itemCountBefore,
          itemCountAfter: itemCountAfter,
          error: error,
          copyKey: error == null ? null : 'appendFailedRetry',
        );
  }
}
