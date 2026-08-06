import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart'
    show DiscoveryFeedRouteRegistry, kFeedSortRecommend;
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/shell/loading/app_request_wait_controller.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_publication_epoch.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/discovery_feed_resident_page_window.dart';
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

void _requireSamePolicyDigest({
  required String? accepted,
  required String? incoming,
}) {
  _requireCanonicalPolicyDigest(accepted);
  _requireCanonicalPolicyDigest(incoming);
  if (accepted != incoming) {
    throw const FormatException(
      'continuation policyDigest must match the accepted feed window',
    );
  }
}

void _requireCanonicalPolicyDigest(String? policyDigest) {
  if (policyDigest != null && !isCanonicalSha256Digest(policyDigest)) {
    throw const FormatException(
      'policyDigest must be a canonical SHA-256 digest',
    );
  }
}

bool _isCanonicalInitialEmptyPage(String channelId, DiscoveryFeedPage page) {
  if (!page.isCanonicalEmpty) {
    return false;
  }
  final requiresActiveRelease =
      CloudRuntimeConfig.requiresReleaseBoundContent ||
      CloudRuntimeConfig.hasCompleteContentBinding;
  return switch (page.emptyReason!) {
    ContentFeedEmptyReason.followingEmpty => channelId == 'following',
    ContentFeedEmptyReason.noActiveRelease =>
      channelId != 'following' && !requiresActiveRelease,
    ContentFeedEmptyReason.noEligibleContent => channelId != 'following',
    ContentFeedEmptyReason.continuationEnd => false,
  };
}

void _requireCanonicalContinuationPage(DiscoveryFeedPage page) {
  final valid = page.items.isEmpty
      ? page.outcome == ContentFeedOutcome.empty &&
            page.emptyReason == ContentFeedEmptyReason.continuationEnd
      : page.outcome == ContentFeedOutcome.content && page.emptyReason == null;
  if (!valid) {
    throw const FormatException(
      'Continuation feed page has an invalid outcome envelope',
    );
  }
}

/// 首屏响应未满足 canonical content/empty envelope 时的本地协议失败。
///
/// 健康空内容必须携带合法的 `outcome=empty + emptyReason`，不会进入此分支；
/// `following` 的合法空态和分页 continuation end 同样不会调用此构造器。
RuntimeFailure discoveryFeedInitialPageProtocolFailure(String channelId) {
  return RuntimeFailure(
    code: RuntimeFailureCodes.appContractInvalidResponse,
    semanticReason: 'discovery_feed_initial_page_protocol_violation',
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.contract,
    nature: RuntimeFailureNature.bug,
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

final class DiscoveryFeedLocalPostRemoval {
  const DiscoveryFeedLocalPostRemoval({
    required this.post,
    required this.visibleIndex,
    this.residentPlacement,
  });

  final ContentPostViewData post;
  final int visibleIndex;
  final DiscoveryFeedVisiblePostPlacement? residentPlacement;
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
    this.policyDigest,
    this.emptyReason,
    this.canRestorePreviousPage = false,
    this.hasBufferedNextPage = false,
    this.residentPageCount = 0,
    this.retainedPageCount = 0,
    this.isLoading = false,
    this.isRefreshing = false,
    this.isAppending = false,
    this.isPrepending = false,
    this.isSlow = false,
    this.blockingError,
    this.staleDataError,
    this.appendError,
    this.prependError,
  });

  final List<ContentPostViewData> items;

  /// 混合对象卡（B4 插卡模式）：anchorIndex 为 items 全量列表中的插入位。
  /// 只随首刷下发（分页续接不重复注入）。
  final List<FeedObjectCard> objectCards;
  final List<String> seenItemIds;
  final String? nextCursor;

  /// 服务端权威下发的归因 id（frq_ 前缀）；分页回显、行为事件透传。
  final String? feedRequestId;

  /// 当前 feed window 的唯一推荐策略摘要；来源未提供时为 null。
  final String? policyDigest;

  /// 服务端确认本次查询健康完成但无内容时的 canonical 原因。
  final ContentFeedEmptyReason? emptyReason;

  /// 当前 resident deque 两侧仍可从同一有界内存窗口恢复的页边界。
  final bool canRestorePreviousPage;
  final bool hasBufferedNextPage;
  final int residentPageCount;
  final int retainedPageCount;

  /// 兼容存量 UI 的等待信号：首屏阻塞加载或分页时为 true。
  ///
  /// 保留正文的后台刷新只由 [isRefreshing] 表达，避免存量 UI
  /// 误显示底部分页 loading。
  final bool isLoading;
  final bool isRefreshing;
  final bool isAppending;
  final bool isPrepending;
  final bool isSlow;
  final Object? blockingError;
  final Object? staleDataError;
  final Object? appendError;
  final Object? prependError;

  bool get hasMore =>
      hasBufferedNextPage || (nextCursor != null && nextCursor!.isNotEmpty);
  Object? get rawError =>
      blockingError ?? staleDataError ?? appendError ?? prependError;
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
    List<ContentPostViewData>? items,
    List<FeedObjectCard>? objectCards,
    List<String>? seenItemIds,
    Object? nextCursor = _unset,
    Object? feedRequestId = _unset,
    Object? policyDigest = _unset,
    Object? emptyReason = _unset,
    bool? canRestorePreviousPage,
    bool? hasBufferedNextPage,
    int? residentPageCount,
    int? retainedPageCount,
    bool? isLoading,
    bool? isRefreshing,
    bool? isAppending,
    bool? isPrepending,
    bool? isSlow,
    Object? blockingError = _unset,
    Object? staleDataError = _unset,
    Object? appendError = _unset,
    Object? prependError = _unset,
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
      policyDigest: identical(policyDigest, _unset)
          ? this.policyDigest
          : policyDigest as String?,
      emptyReason: identical(emptyReason, _unset)
          ? this.emptyReason
          : emptyReason as ContentFeedEmptyReason?,
      canRestorePreviousPage:
          canRestorePreviousPage ?? this.canRestorePreviousPage,
      hasBufferedNextPage: hasBufferedNextPage ?? this.hasBufferedNextPage,
      residentPageCount: residentPageCount ?? this.residentPageCount,
      retainedPageCount: retainedPageCount ?? this.retainedPageCount,
      isLoading: isLoading ?? this.isLoading,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      isAppending: isAppending ?? this.isAppending,
      isPrepending: isPrepending ?? this.isPrepending,
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
      prependError: identical(prependError, _unset)
          ? this.prependError
          : prependError,
    );
  }
}

typedef DiscoveryFeedQuery = ({
  String category,
  String? channel,
  String? identity,
  String? type,
});

enum DiscoveryFeedLoadTerminal {
  content,
  canonicalEmpty,
  retainedContent,
  stillBlocked,
  superseded,
  cancelled,
}

/// 一次 Feed generation 的权威终态；Widget 不得在 await 后再读共享状态猜测结果。
final class DiscoveryFeedLoadResult {
  const DiscoveryFeedLoadResult({
    required this.terminal,
    required this.generation,
    this.failure,
  });

  final DiscoveryFeedLoadTerminal terminal;
  final int generation;
  final Object? failure;
}

/// 将 surface tab id 映射到统一 discovery feed 查询。
///
/// 频道推荐主链路（首页频道）以 [DiscoveryFeedQuery.channel] 路由（服务端进
/// 推荐引擎并按 channelId 归因）；发现页浏览流（moment/photo/video/article tab）
/// 仍以 identity/type 走时间线具名查询，两者互斥。
DiscoveryFeedQuery toDiscoveryFeedQuery(String channelId) {
  final registeredRoute = DiscoveryFeedRouteRegistry.routeForSurface(channelId);
  if (registeredRoute != null) {
    return (
      category: registeredRoute.category,
      channel: registeredRoute.channelId,
      identity: registeredRoute.identity,
      type: registeredRoute.type,
    );
  }
  // 首页频道由 metadata 下发，统一按 channel 语义路由推荐引擎。
  return (category: channelId, channel: channelId, identity: null, type: null);
}

/// 按 channelId 管理多路 feed 的 Notifier
class DiscoveryFeedMapNotifier
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
                !_isCanonicalInitialEmptyPage(channelId, page)) ||
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
        .applyConfirmedPosts(page.items);
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
          .applyConfirmedPosts(dedupedNew);
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
            .applyConfirmedPosts(confirmed);
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
