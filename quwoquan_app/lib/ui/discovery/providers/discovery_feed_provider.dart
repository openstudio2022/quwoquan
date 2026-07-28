import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

const String _discoveryFeedRequestPath = '/content/feed';

CloudException _normalizeDiscoveryFeedError(Object error) {
  if (error is CloudException) return error;
  return CloudErrorMapper.fromException(
    error,
    requestPath: _discoveryFeedRequestPath,
  );
}

/// 推荐首屏成功响应却没有任何可展示内容时的本地一致性失败。
///
/// 该失败由 App 根据响应不变量判定，不填充 status/request/trace 等服务端 wire 字段。
/// `following` 的合法空态和分页 continuation end 不会调用此构造器。
RuntimeFailure discoveryFeedInitialEmptyPageFailure(String channelId) {
  return RuntimeFailure(
    code: ContentErrorCode.requiredDependencyUnavailable.code,
    semanticReason: 'discovery_feed_initial_page_empty',
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'content.discovery_feed',
      functionModule: 'discovery_feed_provider',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'channelId', value: channelId),
      ],
    ),
    recovery: const RuntimeRecoveryDirective(
      action: 'retry',
      disruptionLevel: 'fullPage',
    ),
  );
}

/// 单类 feed 状态：items + nextCursor
class DiscoveryFeedState {
  static const Object _unset = Object();

  const DiscoveryFeedState({
    this.items = const [],
    this.objectCards = const [],
    this.seenItemIds = const [],
    this.nextCursor,
    this.feedRequestId,
    this.isLoading = false,
    this.isSlow = false,
    this.blockingError,
    this.staleDataError,
    this.appendError,
  });

  final List<PostBaseDto> items;

  /// 混合对象卡（B4 插卡模式）：anchorIndex 为 items 全量列表中的插入位。
  /// 只随首刷下发（分页续接不重复注入）。
  final List<FeedObjectCardDto> objectCards;
  final List<String> seenItemIds;
  final String? nextCursor;

  /// 服务端权威下发的归因 id（frq_ 前缀）；分页回显、行为事件透传。
  final String? feedRequestId;
  final bool isLoading;
  final bool isSlow;
  final Object? blockingError;
  final Object? staleDataError;
  final Object? appendError;

  bool get hasMore => nextCursor != null && nextCursor!.isNotEmpty;
  Object? get rawError => blockingError ?? staleDataError ?? appendError;
  String? get error => errorMessage;
  String? get errorMessage {
    final currentError = rawError;
    if (currentError == null) {
      return null;
    }
    if (currentError is String && currentError.trim().isNotEmpty) {
      return currentError.trim();
    }
    final message = runtimeErrorDisplayMessage(currentError).trim();
    if (message.isNotEmpty) {
      return message;
    }
    return null;
  }

  DiscoveryFeedState copyWith({
    List<PostBaseDto>? items,
    List<FeedObjectCardDto>? objectCards,
    List<String>? seenItemIds,
    Object? nextCursor = _unset,
    Object? feedRequestId = _unset,
    bool? isLoading,
    bool? isSlow,
    Object? blockingError = _unset,
    Object? staleDataError = _unset,
    Object? appendError = _unset,
  }) {
    return DiscoveryFeedState(
      items: items ?? this.items,
      objectCards: objectCards ?? this.objectCards,
      seenItemIds: seenItemIds ?? this.seenItemIds,
      nextCursor: identical(nextCursor, _unset)
          ? this.nextCursor
          : nextCursor as String?,
      feedRequestId: identical(feedRequestId, _unset)
          ? this.feedRequestId
          : feedRequestId as String?,
      isLoading: isLoading ?? this.isLoading,
      isSlow: isSlow ?? this.isSlow,
      blockingError: identical(blockingError, _unset)
          ? this.blockingError
          : blockingError,
      staleDataError: identical(staleDataError, _unset)
          ? this.staleDataError
          : staleDataError,
      appendError: identical(appendError, _unset)
          ? this.appendError
          : appendError,
    );
  }
}

typedef DiscoveryFeedQuery = ({
  String category,
  String? channel,
  String? identity,
  String? type,
});

/// 将 surface tab id 映射到统一 discovery feed 查询。
///
/// 频道推荐主链路（首页频道）以 [DiscoveryFeedQuery.channel] 路由（服务端进
/// 推荐引擎并按 channelId 归因）；发现页浏览流（moment/photo/video/article tab）
/// 仍以 identity/type 走时间线具名查询，两者互斥。
DiscoveryFeedQuery toDiscoveryFeedQuery(String channelId) {
  switch (channelId) {
    case 'following':
      return (
        category: 'following',
        channel: 'following',
        identity: null,
        type: null,
      );
    case 'moment':
      return (
        category: 'moment',
        channel: null,
        identity: 'moment',
        type: null,
      );
    case 'work':
    case 'works':
      return (category: 'work', channel: null, identity: 'work', type: null);
    case 'photo':
      return (
        category: 'photo',
        channel: null,
        identity: 'work',
        type: 'image',
      );
    case 'video':
      return (
        category: 'video',
        channel: null,
        identity: 'work',
        type: 'video',
      );
    case 'article':
      return (
        category: 'article',
        channel: null,
        identity: 'work',
        type: 'article',
      );
    default:
      // 首页频道（recommend/campus/travel/...）：channel 语义路由推荐引擎。
      return (
        category: channelId,
        channel: channelId,
        identity: null,
        type: null,
      );
  }
}

/// 按 channelId 管理多路 feed 的 Notifier
class DiscoveryFeedMapNotifier
    extends Notifier<Map<String, AsyncValue<DiscoveryFeedState>>> {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
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
      for (final controller in _waitControllers.values) {
        controller.dispose();
      }
      _waitControllers.clear();
    });
    return {};
  }

  final Map<String, AppRequestWaitController> _waitControllers =
      <String, AppRequestWaitController>{};

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

  Future<void> load(String channelId, {bool force = false}) async {
    final currentValue = state[channelId]?.value;
    if (!force && currentValue != null && currentValue.items.isNotEmpty) {
      return;
    }
    final repo = ref.read(contentDiscoveryFeedQueryProvider);
    final query = _resolveQuery(channelId);
    final feedSession = ref.read(feedSessionProvider.notifier);
    final sessionId = feedSession.sessionId;
    final controller = _waitControllers.putIfAbsent(
      channelId,
      AppRequestWaitController.new,
    );
    controller.cancel();
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
          isSlow: false,
          blockingError: null,
          staleDataError: null,
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
      if (!controller.isCurrent(generation)) return;
      final hasRetainedItems = currentValue?.items.isNotEmpty ?? false;
      final hasInitialEmptyProtocolViolation =
          channelId != 'following' &&
          page.items.isEmpty &&
          page.cacheFallbackError == null;
      if (hasInitialEmptyProtocolViolation) {
        final error = discoveryFeedInitialEmptyPageFailure(channelId);
        developer.log(
          'Initial discovery feed page contained no displayable items.',
          name: 'DiscoveryFeed',
          error: error,
        );
        state = {
          ...state,
          channelId: AsyncData(
            hasRetainedItems
                ? currentValue!.copyWith(
                    isLoading: false,
                    isSlow: false,
                    blockingError: null,
                    staleDataError: error,
                    appendError: null,
                  )
                : DiscoveryFeedState(
                    blockingError: error,
                    isLoading: false,
                    isSlow: false,
                  ),
          ),
        };
        _recordPageState(
          channelId,
          phase: hasRetainedItems ? 'cacheFallback' : 'blockingFailure',
          source: hasRetainedItems ? 'retained' : 'localConsistency',
          error: error,
          copyKey: hasRetainedItems ? 'homeCacheFallback' : null,
          hasCache: hasRetainedItems,
          itemCount: hasRetainedItems ? currentValue!.items.length : 0,
          requestId: hasRetainedItems ? currentValue!.feedRequestId : null,
        );
        controller.complete(generation);
        return;
      }
      // 采纳服务端下发的归因 id，使后续曝光/点击/打开复用同一 feedRequestId。
      feedSession.adoptServerFeedRequestId(
        page.feedRequestId,
        rankingVersion: page.rankingVersion,
        reasonVersion: page.reasonVersion,
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(page.items);
      final seen = page.items
          .map((item) => item.id)
          .where((id) => id.isNotEmpty)
          .toList(growable: false);
      final fallbackError = page.cacheFallbackError == null
          ? null
          : _normalizeDiscoveryFeedError(page.cacheFallbackError!);
      final hasDisplayableCache = page.items.isNotEmpty;
      state = {
        ...state,
        channelId: AsyncData(
          DiscoveryFeedState(
            items: page.items,
            objectCards: page.objectCards,
            seenItemIds: seen,
            nextCursor: page.nextCursor,
            feedRequestId: page.feedRequestId,
            blockingError: fallbackError != null && !hasDisplayableCache
                ? fallbackError
                : null,
            staleDataError: fallbackError != null && hasDisplayableCache
                ? fallbackError
                : null,
            isLoading: false,
            isSlow: false,
          ),
        ),
      };
      final phase = fallbackError == null
          ? 'onlineSuccess'
          : hasDisplayableCache
          ? 'cacheFallback'
          : 'blockingFailure';
      _recordPageState(
        channelId,
        phase: phase,
        source: fallbackError != null && hasDisplayableCache
            ? 'cache'
            : 'online',
        error: fallbackError,
        copyKey: fallbackError != null && hasDisplayableCache
            ? 'homeCacheFallback'
            : null,
        hasCache: fallbackError != null && hasDisplayableCache,
        cacheAgeMs: page.cacheAgeMs,
        itemCount: page.items.length,
        requestId: page.feedRequestId,
      );
      controller.complete(generation);
    } catch (e, st) {
      if (!controller.isCurrent(generation)) return;
      final error = _normalizeDiscoveryFeedError(e);
      if (error.runtimeFailure.kind == RuntimeFailureKind.cancelled) {
        state = {
          ...state,
          channelId: AsyncData(
            (currentValue ?? const DiscoveryFeedState()).copyWith(
              isLoading: false,
              isSlow: false,
              blockingError: null,
              staleDataError: null,
            ),
          ),
        };
        return;
      }
      developer.log(
        'load error: $error',
        name: 'DiscoveryFeed',
        error: error,
        stackTrace: st,
      );
      if (currentValue != null && currentValue.items.isNotEmpty) {
        state = {
          ...state,
          channelId: AsyncData(
            currentValue.copyWith(
              isLoading: false,
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
          itemCount: currentValue.items.length,
          requestId: currentValue.feedRequestId,
        );
        return;
      }
      state = {
        ...state,
        channelId: AsyncData(
          DiscoveryFeedState(blockingError: error, isLoading: false),
        ),
      };
      _recordPageState(
        channelId,
        phase: 'blockingFailure',
        source: 'online',
        error: error,
        hasCache: false,
        itemCount: 0,
      );
    } finally {
      controller.complete(generation);
    }
  }

  Future<void> appendNextPage(String channelId) async {
    final current = state[channelId];
    final value = current?.value;
    if (value == null ||
        value.nextCursor == null ||
        value.nextCursor!.isEmpty ||
        value.isLoading) {
      return;
    }
    final controller = _waitControllers.putIfAbsent(
      channelId,
      AppRequestWaitController.new,
    );
    controller.cancel();
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
        cursor: value.nextCursor,
        sessionId: sessionId,
        feedRequestId: value.feedRequestId,
        cancellation: cancellation,
        deadlineAt: DateTime.now().add(
          AppRequestWaitTimings.foregroundReadDeadline,
        ),
      );
      if (!controller.isCurrent(generation)) return;
      feedSession.adoptServerFeedRequestId(
        page.feedRequestId,
        rankingVersion: page.rankingVersion,
        reasonVersion: page.reasonVersion,
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .applyConfirmedPosts(page.items);
      final seen = value.seenItemIds.toSet();
      final dedupedNew = page.items
          .where((item) => !seen.contains(item.id))
          .toList(growable: false);
      final merged = <PostBaseDto>[...value.items, ...dedupedNew];
      final mergedSeen = <String>[
        ...value.seenItemIds,
        ...dedupedNew.map((e) => e.id),
      ];
      state = {
        ...state,
        channelId: AsyncData(
          value.copyWith(
            items: merged,
            seenItemIds: mergedSeen,
            nextCursor: page.nextCursor,
            feedRequestId: page.feedRequestId ?? value.feedRequestId,
            isLoading: false,
            appendError: null,
            staleDataError: null,
          ),
        ),
      };
      _recordAppend(
        channelId,
        result: 'success',
        cursorPresent: true,
        hasMore: page.nextCursor?.isNotEmpty ?? false,
        itemCountBefore: value.items.length,
        itemCountAfter: merged.length,
      );
      controller.complete(generation);
    } catch (e, st) {
      if (!controller.isCurrent(generation)) return;
      final error = _normalizeDiscoveryFeedError(e);
      if (error.runtimeFailure.kind == RuntimeFailureKind.cancelled) {
        state = {
          ...state,
          channelId: AsyncData(value.copyWith(isLoading: false)),
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
          value.copyWith(isLoading: false, appendError: error),
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

  Map<String, ({PostBaseDto post, int index})> removePostLocally(
    String postId,
  ) {
    final normalized = postId.trim();
    if (normalized.isEmpty) {
      return const <String, ({PostBaseDto post, int index})>{};
    }
    final removed = <String, ({PostBaseDto post, int index})>{};
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
      if (removedIndex >= 0) {
        removed[entry.key] = (
          post: value.items[removedIndex],
          index: removedIndex,
        );
      }
      final filteredItems = value.items
          .where((item) => item.id != normalized)
          .toList(growable: false);
      final filteredSeen = value.seenItemIds
          .where((id) => id != normalized)
          .toList(growable: false);
      next[entry.key] = AsyncData(
        value.copyWith(items: filteredItems, seenItemIds: filteredSeen),
      );
    }
    state = next;
    return removed;
  }

  void restorePostsLocally(
    Map<String, ({PostBaseDto post, int index})> removed,
  ) {
    if (removed.isEmpty) return;
    final next = Map<String, AsyncValue<DiscoveryFeedState>>.from(state);
    for (final entry in removed.entries) {
      final current = state[entry.key]?.value;
      if (current == null ||
          current.items.any((item) => item.id == entry.value.post.id)) {
        continue;
      }
      final items = List<PostBaseDto>.from(current.items);
      final index = entry.value.index.clamp(0, items.length).toInt();
      items.insert(index, entry.value.post);
      next[entry.key] = AsyncData(
        current.copyWith(
          items: items,
          seenItemIds: <String>{
            ...current.seenItemIds,
            entry.value.post.id,
          }.toList(growable: false),
        ),
      );
    }
    state = next;
  }
}

/// 全量 feed 状态 Map 的 Provider
final discoveryFeedMapProvider =
    NotifierProvider<
      DiscoveryFeedMapNotifier,
      Map<String, AsyncValue<DiscoveryFeedState>>
    >(DiscoveryFeedMapNotifier.new);

/// 按 tab (photo/video) 读取当前 feed；首次访问时需调用 notifier.load(channelId)
final discoveryFeedProvider =
    Provider.family<AsyncValue<DiscoveryFeedState>, String>((ref, channelId) {
      final map = ref.watch(discoveryFeedMapProvider);
      return map[channelId] ?? const AsyncValue.loading();
    });
