part of 'discovery_feed_provider.dart';

abstract class _DiscoveryFeedMapPaginationLifecycle
    extends _DiscoveryFeedMapLoadingCore {
  Future<void> appendNextPage(String channelId) async {
    final current = state[channelId];
    final value = current?.value;
    if (value == null ||
        value.isLoading ||
        value.isRefreshing ||
        value.isAppending ||
        value.isPrepending) {
      return;
    }
    if (value.hasBufferedNextPage && _restoreBufferedNextPage(channelId)) {
      return;
    }
    // `DiscoveryFeedState.nextCursor` is a render snapshot. A long-idle page
    // can cross the server cursor expiry without another provider rebuild, so
    // every Remote continuation must re-read the live bounded-window truth.
    // This prevents an avoidable invalid-cursor request and clears the stale
    // affordance immediately when the user reaches the boundary.
    final residentWindow = _residentPageWindows[channelId];
    final incomingCursor = residentWindow?.nextCursor;
    if (incomingCursor == null || incomingCursor.isEmpty) {
      if (residentWindow != null && (value.nextCursor?.isNotEmpty ?? false)) {
        state = {
          ...state,
          channelId: AsyncData(_withResidentPageWindow(value, residentWindow)),
        };
      }
      return;
    }
    final controller = _appendWaitControllers.putIfAbsent(
      channelId,
      AppRequestWaitController.new,
    );
    final cancellation = CloudOperationCancellationSignal();
    late final int generation;
    generation = controller.start(
      mode: AppRequestWaitMode.foreground,
      showSlowHint: false,
      cancellation: cancellation,
      onTimeout: (_) {
        final latest = state[channelId]?.value;
        if (latest == null) return;
        state = {
          ...state,
          channelId: AsyncData(
            latest.copyWith(
              isLoading: false,
              isAppending: false,
              appendError: _normalizeDiscoveryFeedError(
                TimeoutException(
                  'Home pagination exceeded the 6 second budget.',
                ),
              ),
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
          hasCache: true,
          itemCount: value.items.length,
          durationMs: durationMilliseconds,
        );
      },
    );
    state = {
      ...state,
      channelId: AsyncData(
        value.copyWith(
          isLoading: true,
          isRefreshing: false,
          isAppending: true,
          appendError: null,
          staleDataError: null,
        ),
      ),
    };
    _recordAppend(
      channelId,
      result: 'loading',
      cursorPresent: true,
      hasMore: true,
      itemCountBefore: value.items.length,
    );
    try {
      final repo = ref.read(contentDiscoveryFeedQueryProvider);
      final query = _resolveQuery(channelId);
      final feedSession = ref.read(feedSessionProvider.notifier);
      final sessionId = feedSession.sessionId;
      // 分页回显首刷服务端下发的 feedRequestId，保持同一 feed 会话归因连续。
      final page = await repo.listDiscoveryFeedPage(
        category: query.category,
        channelId: query.channel,
        identity: query.identity,
        type: query.type,
        sort: kFeedSortRecommend,
        limit: 20,
        cursor: incomingCursor,
        sessionId: sessionId,
        feedRequestId: value.feedRequestId,
        cancellation: cancellation,
        deadlineAt: DateTime.now().add(
          AppRequestWaitTimings.foregroundReadDeadline,
        ),
      );
      if (!controller.isCurrent(generation)) return;
      _requireCanonicalContinuationPage(page);
      final currentResidentWindow = _residentPageWindows[channelId];
      if (currentResidentWindow == null) {
        throw StateError(
          'missing resident page window for loaded channel $channelId',
        );
      }
      _requireSamePolicyDigest(
        accepted: value.policyDigest,
        incoming: page.policyDigest,
      );
      // Remote forward navigation can legitimately revisit a page that was
      // previously viewed and then evicted during a deep backslide. Suppress
      // only identities still retained in the bounded deque; the historical
      // seen LRU is observability state, not a second pagination truth source.
      final retained = currentResidentWindow.retainedPostIds;
      final dedupedNew = page.items
          .where((item) => !retained.contains(item.id.trim()))
          .toList(growable: false);
      final nextWindow = currentResidentWindow.appendRemotePage(
        DiscoveryFeedResidentPage.fromEnvelope(
          incomingCursor: incomingCursor,
          page: page,
          visibleItems: dedupedNew,
        ),
      );
      // 单页预算与 deque 不变量通过后才采纳服务端归因；超预算响应必须在
      // feed session / interaction projection 等任何业务副作用前 fail-closed。
      feedSession.adoptServerFeedRequestId(page.feedRequestId);
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(
            dedupedNew,
            pendingLikePostIds: ref.read(pendingLikeSyncPostIdsProvider),
          );
      final mergedSeen = _boundedSeenItemIds(
        value.seenItemIds,
        dedupedNew.map((item) => item.id),
      );
      final fallbackError = page.cacheFallbackError == null
          ? null
          : _normalizeDiscoveryFeedError(page.cacheFallbackError!);
      _residentPageWindows[channelId] = nextWindow;
      state = {
        ...state,
        channelId: AsyncData(
          _withResidentPageWindow(
            value.copyWith(
              seenItemIds: mergedSeen,
              feedRequestId: page.feedRequestId ?? value.feedRequestId,
              policyDigest: page.policyDigest,
              isLoading: false,
              isRefreshing: false,
              isAppending: false,
              // 非首屏 QuerySnapshot 在远端失败时仍可提供可见续页，但它是
              // stale/offline fallback，不得包装成 online success。保留 append
              // 恢复入口，用户可在网络恢复后重试同一 continuation。
              appendError: fallbackError,
              staleDataError: null,
            ),
            nextWindow,
          ),
        ),
      };
      _recordAppend(
        channelId,
        result: fallbackError == null ? 'success' : 'cacheFallback',
        cursorPresent: true,
        hasMore: page.nextCursor?.isNotEmpty ?? false,
        itemCountBefore: value.items.length,
        itemCountAfter: nextWindow.visibleItems.length,
        error: fallbackError,
        copyKey: fallbackError == null ? null : 'appendFailedRetry',
      );
      if (fallbackError != null) {
        _recordPageState(
          channelId,
          phase: 'cacheFallback',
          source: 'cache',
          error: fallbackError,
          copyKey: 'appendFailedRetry',
          hasCache: true,
          cacheAgeMs: page.cacheAgeMs,
          itemCount: nextWindow.visibleItems.length,
          requestId: page.feedRequestId ?? value.feedRequestId,
        );
      }
      controller.complete(generation);
    } catch (e, st) {
      if (!controller.isCurrent(generation)) return;
      final error = _normalizeDiscoveryFeedError(e);
      if (error.runtimeFailure.kind == RuntimeFailureKind.cancelled) {
        state = {
          ...state,
          channelId: AsyncData(
            value.copyWith(isLoading: false, isAppending: false),
          ),
        };
        return;
      }
      developer.log(
        'append error: $error',
        name: 'DiscoveryFeed',
        error: error,
        stackTrace: st,
      );
      state = {
        ...state,
        channelId: AsyncData(
          value.copyWith(
            isLoading: false,
            isAppending: false,
            appendError: error,
          ),
        ),
      };
      _recordAppend(
        channelId,
        result: 'failure',
        cursorPresent: true,
        hasMore: value.nextCursor?.isNotEmpty ?? false,
        itemCountBefore: value.items.length,
        itemCountAfter: value.items.length,
        error: error,
        copyKey: 'appendFailedRetry',
      );
    } finally {
      controller.complete(generation);
    }
  }

  /// 从同一有界 resident window 向前恢复一个已加载完整页。
  ///
  /// 该操作不发 Remote 请求、不解析 cursor；Widget 必须先保存可见 Post 锚点，
  /// items 变化后再以 stable identity 做 geometry 校正。
  bool restorePreviousPage(String channelId) {
    final normalized = channelId.trim();
    final value = state[normalized]?.value;
    final currentWindow = _residentPageWindows[normalized];
    if (value == null ||
        currentWindow == null ||
        value.isLoading ||
        value.isRefreshing ||
        value.isAppending ||
        value.isPrepending) {
      return false;
    }
    final restored = currentWindow.restorePreviousPage();
    if (restored == null) {
      return false;
    }
    _residentPageWindows[normalized] = restored;
    state = {
      ...state,
      normalized: AsyncData(
        _withResidentPageWindow(
          value.copyWith(
            isLoading: false,
            isRefreshing: false,
            isAppending: false,
          ),
          restored,
        ),
      ),
    };
    return true;
  }

  /// 先从内存窗口恢复；内存前页耗尽后，使用服务端稳定 previous cursor 回取
  /// 已交付页。回取只按当前 retained Post 去重，不能用历史 seen 集合误删已被
  /// 有界窗口淘汰、现在需要重新展示的 Post。
  Future<bool> prependPreviousPage(String channelId) async {
    final normalized = channelId.trim();
    if (normalized.isEmpty) {
      return false;
    }
    if (restorePreviousPage(normalized)) {
      return true;
    }
    final initialValue = state[normalized]?.value;
    final initialWindow = _residentPageWindows[normalized];
    final initialCursor = initialWindow?.previousCursor;
    if (initialValue == null ||
        initialWindow == null ||
        initialCursor == null ||
        initialCursor.isEmpty ||
        initialValue.isLoading ||
        initialValue.isRefreshing ||
        initialValue.isAppending ||
        initialValue.isPrepending) {
      return false;
    }
    var window = initialWindow;
    String? cursor = initialCursor;

    final controller = _prependWaitControllers.putIfAbsent(
      normalized,
      AppRequestWaitController.new,
    );
    final cancellation = CloudOperationCancellationSignal();
    late final int generation;
    generation = controller.start(
      mode: AppRequestWaitMode.foreground,
      showSlowHint: false,
      cancellation: cancellation,
      onTimeout: (_) {
        final latest = state[normalized]?.value;
        if (latest == null) return;
        state = {
          ...state,
          normalized: AsyncData(
            latest.copyWith(
              isPrepending: false,
              prependError: _normalizeDiscoveryFeedError(
                TimeoutException(
                  'Home previous-page recovery exceeded the 6 second budget.',
                ),
              ),
            ),
          ),
        };
      },
    );
    state = {
      ...state,
      normalized: AsyncData(
        initialValue.copyWith(isPrepending: true, prependError: null),
      ),
    };

    final repo = ref.read(contentDiscoveryFeedQueryProvider);
    final query = _resolveQuery(normalized);
    final feedSession = ref.read(feedSessionProvider.notifier);
    final sessionId = feedSession.sessionId;
    final deadlineAt = DateTime.now().add(
      AppRequestWaitTimings.foregroundReadDeadline,
    );
    final confirmed = <ContentPostViewData>[];
    Object? fallbackError;
    try {
      // 已交付页可能因内容删除/权限变化而收缩为空；最多跨过四个空页，避免
      // 一次顶部手势形成无界网络循环。
      for (var attempt = 0; attempt < 4; attempt += 1) {
        final page = await repo.listDiscoveryFeedPage(
          category: query.category,
          channelId: query.channel,
          identity: query.identity,
          type: query.type,
          sort: kFeedSortRecommend,
          limit: homeFeedPageItemLimit,
          cursor: cursor,
          sessionId: sessionId,
          feedRequestId: initialValue.feedRequestId,
          cancellation: cancellation,
          deadlineAt: deadlineAt,
        );
        if (!controller.isCurrent(generation)) return false;
        _requireCanonicalContinuationPage(page);
        _requireSamePolicyDigest(
          accepted: initialValue.policyDigest,
          incoming: page.policyDigest,
        );
        final retained = window.retainedPostIds;
        final visible = page.items
            .where((item) => !retained.contains(item.id.trim()))
            .toList(growable: false);
        final deliveredPage = DiscoveryFeedResidentPage.fromEnvelope(
          incomingCursor: cursor,
          page: page,
          visibleItems: visible,
        );
        if (visible.isNotEmpty) {
          window = window.prependRemotePage(deliveredPage);
          confirmed.addAll(visible);
        }
        feedSession.adoptServerFeedRequestId(page.feedRequestId);
        fallbackError = page.cacheFallbackError;
        cursor = page.previousCursor?.trim();
        if (visible.isNotEmpty || cursor == null || cursor.isEmpty) {
          break;
        }
      }
      if (!controller.isCurrent(generation)) return false;
      if (confirmed.isEmpty) {
        // Persist the advanced/exhausted remote boundary on the first visible
        // page without inserting zero-item pages into the resident deque.
        window = window.withRemotePreviousCursor(cursor);
      }
      if (confirmed.isNotEmpty) {
        ref
            .read(postInteractionStateProvider.notifier)
            .applyConfirmedPosts(
              confirmed,
              pendingLikePostIds: ref.read(pendingLikeSyncPostIdsProvider),
            );
      }
      final normalizedFallback = fallbackError == null
          ? null
          : _normalizeDiscoveryFeedError(fallbackError);
      _residentPageWindows[normalized] = window;
      state = {
        ...state,
        normalized: AsyncData(
          _withResidentPageWindow(
            initialValue.copyWith(
              seenItemIds: _boundedSeenItemIds(
                initialValue.seenItemIds,
                confirmed.map((item) => item.id),
              ),
              isLoading: false,
              isRefreshing: false,
              isAppending: false,
              isPrepending: false,
              prependError: normalizedFallback,
              staleDataError: null,
            ),
            window,
          ),
        ),
      };
      _recordPreviousPage(
        normalized,
        result: normalizedFallback == null ? 'success' : 'cacheFallback',
        itemCountBefore: initialValue.items.length,
        itemCountAfter: window.visibleItems.length,
        error: normalizedFallback,
      );
      controller.complete(generation);
      return confirmed.isNotEmpty;
    } catch (error, stackTrace) {
      if (!controller.isCurrent(generation)) return false;
      final normalizedError = _normalizeDiscoveryFeedError(error);
      if (normalizedError.runtimeFailure.kind == RuntimeFailureKind.cancelled) {
        state = {
          ...state,
          normalized: AsyncData(initialValue.copyWith(isPrepending: false)),
        };
        return false;
      }
      developer.log(
        'prepend error: $normalizedError',
        name: 'DiscoveryFeed',
        error: normalizedError,
        stackTrace: stackTrace,
      );
      state = {
        ...state,
        normalized: AsyncData(
          initialValue.copyWith(
            isPrepending: false,
            prependError: normalizedError,
          ),
        ),
      };
      _recordPreviousPage(
        normalized,
        result: 'failure',
        itemCountBefore: initialValue.items.length,
        itemCountAfter: initialValue.items.length,
        error: normalizedError,
      );
      return false;
    } finally {
      controller.complete(generation);
    }
  }

  bool _restoreBufferedNextPage(String channelId) {
    final normalized = channelId.trim();
    final value = state[normalized]?.value;
    final currentWindow = _residentPageWindows[normalized];
    if (value == null || currentWindow == null) {
      return false;
    }
    final restored = currentWindow.restoreNextPage();
    if (restored == null) {
      return false;
    }
    _residentPageWindows[normalized] = restored;
    state = {
      ...state,
      normalized: AsyncData(
        _withResidentPageWindow(
          value.copyWith(
            isLoading: false,
            isRefreshing: false,
            isAppending: false,
            appendError: null,
          ),
          restored,
        ),
      ),
    };
    return true;
  }

  Map<String, DiscoveryFeedLocalPostRemoval> removePostLocally(String postId) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return const <String, DiscoveryFeedLocalPostRemoval>{};
    }
    final removed = <String, DiscoveryFeedLocalPostRemoval>{};
    final next = <String, AsyncValue<DiscoveryFeedState>>{};
    for (final entry in state.entries) {
      final value = entry.value.value;
      if (value == null) {
        next[entry.key] = entry.value;
        continue;
      }
      final removedIndex = value.items.indexWhere(
        (item) => item.id == normalized,
      );
      final residentWindow = _residentPageWindows[entry.key];
      if (removedIndex >= 0) {
        removed[entry.key] = DiscoveryFeedLocalPostRemoval(
          post: value.items[removedIndex],
          visibleIndex: removedIndex,
          residentPlacement: residentWindow?.visiblePostPlacement(normalized),
        );
      }
      final filteredItems = value.items
          .where((item) => item.id != normalized)
          .toList(growable: false);
      final filteredSeen = value.seenItemIds
          .where((id) => id != normalized)
          .toList(growable: false);
      if (residentWindow != null) {
        final nextWindow = residentWindow.removePost(normalized);
        _residentPageWindows[entry.key] = nextWindow;
        next[entry.key] = AsyncData(
          _withResidentPageWindow(
            value.copyWith(seenItemIds: filteredSeen),
            nextWindow,
          ),
        );
        continue;
      }
      next[entry.key] = AsyncData(
        value.copyWith(items: filteredItems, seenItemIds: filteredSeen),
      );
    }
    state = next;
    return removed;
  }

  void restorePostsLocally(Map<String, DiscoveryFeedLocalPostRemoval> removed) {
    if (removed.isEmpty) return;
    final next = Map<String, AsyncValue<DiscoveryFeedState>>.from(state);
    for (final entry in removed.entries) {
      final current = state[entry.key]?.value;
      if (current == null ||
          current.items.any((item) => item.id == entry.value.post.id)) {
        continue;
      }
      final items = List<ContentPostViewData>.from(current.items);
      final index = entry.value.visibleIndex.clamp(0, items.length).toInt();
      final residentWindow = _residentPageWindows[entry.key];
      if (residentWindow != null) {
        final placement = entry.value.residentPlacement;
        if (placement == null) {
          continue;
        }
        final nextWindow = residentWindow.restoreVisiblePost(
          placement: placement,
          post: entry.value.post,
        );
        if (identical(nextWindow, residentWindow)) {
          continue;
        }
        _residentPageWindows[entry.key] = nextWindow;
        next[entry.key] = AsyncData(
          _withResidentPageWindow(
            current.copyWith(
              seenItemIds: _boundedSeenItemIds(current.seenItemIds, <String>[
                entry.value.post.id,
              ]),
            ),
            nextWindow,
          ),
        );
        continue;
      }
      items.insert(index, entry.value.post);
      next[entry.key] = AsyncData(
        current.copyWith(
          items: items,
          seenItemIds: _boundedSeenItemIds(current.seenItemIds, <String>[
            entry.value.post.id,
          ]),
        ),
      );
    }
    state = next;
  }

  /// 频道离开可见 surface 时终止该频道自己的 refresh/append generation。
  ///
  /// 已有内容仍保留，供锚点恢复；空的半成品状态移除，下一次进入会重新加载。
  /// resident deque 已把可见 Post 约束在四个完整页；在服务端尚无 previous
  /// boundary cursor 前，频道离开时禁止进一步裁掉这些页，否则无法从
  /// QuerySnapshot 精确恢复远端排序与回滑位置。
  void deactivateChannel(String channelId) {
    final normalized = channelId.trim();
    if (normalized.isEmpty) {
      return;
    }
    cancelChannelRequests(normalized);

    final current = state[normalized];
    final value = current?.value;
    if (value == null || value.items.isEmpty) {
      _residentPageWindows.remove(normalized);
      if (state.containsKey(normalized)) {
        final next = Map<String, AsyncValue<DiscoveryFeedState>>.from(state)
          ..remove(normalized);
        state = next;
      }
      return;
    }
    state = {
      ...state,
      normalized: AsyncData(
        value.copyWith(
          isLoading: false,
          isRefreshing: false,
          isAppending: false,
          isPrepending: false,
          isSlow: false,
        ),
      ),
    };
  }

  /// 仅撤销目标频道的在途 generation，不发布新的 Provider 状态。
  ///
  /// Widget `dispose` 处于 element tree finalization，Riverpod 禁止在该阶段
  /// 写入状态；完整的频道切换仍调用 [deactivateChannel]，页面销毁只调用本方法。
  void cancelChannelRequests(String channelId) {
    final normalized = channelId.trim();
    if (normalized.isEmpty) {
      return;
    }
    final refresh = _refreshWaitControllers.remove(normalized);
    final append = _appendWaitControllers.remove(normalized);
    final prepend = _prependWaitControllers.remove(normalized);
    refresh?.dispose();
    append?.dispose();
    prepend?.dispose();
  }
}
