import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart'
    show DiscoveryFeedRouteRegistry, kFeedSortRecommend;
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/discovery_feed_load_result.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/shell/loading/app_request_wait_controller.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/discovery_feed_resident_page_window.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

export 'package:quwoquan_app/service/content_service/content/post/application/public/discovery_feed_load_result.dart';

part 'discovery_feed_loading.dart';
part 'discovery_feed_pagination_lifecycle.dart';

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

bool _isCanonicalInitialEmptyPage(
  String channelId,
  DiscoveryFeedPage page, {
  required ContentReleaseRequirement releaseRequirement,
}) {
  if (!page.isCanonicalEmpty) {
    return false;
  }
  final requiresActiveRelease =
      releaseRequirement == ContentReleaseRequirement.required;
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
class DiscoveryFeedMapNotifier extends _DiscoveryFeedMapPaginationLifecycle {}

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
