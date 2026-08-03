import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentFeedEmptyReason, ContentFeedOutcome, FeedObjectCard;

/// 首页发现流强类型 envelope。
///
/// 承载分页 items + 服务端权威下发的归因上下文（feedRequestId / policyDigest）。
/// feedRequestId 由 content-service 随响应下发；端侧只读、回显（分页）并透传
/// 后续行为事件，不再由端侧自造。
class DiscoveryFeedPage {
  const DiscoveryFeedPage({
    required this.items,
    this.outcome = ContentFeedOutcome.content,
    this.emptyReason,
    this.objectCards = const <FeedObjectCard>[],
    this.nextCursor,
    this.previousCursor,
    this.paginationExpiresAt,
    this.feedRequestId,
    this.policyDigest,
    this.cacheFallbackError,
    this.cacheAgeMs,
    this.revalidation,
  });

  final List<ContentPostViewData> items;
  final ContentFeedOutcome outcome;
  final ContentFeedEmptyReason? emptyReason;

  /// 混合对象卡（B4 插卡模式）：anchorIndex 指示插入在 items[anchorIndex] 之前；
  /// 空即本页无对象卡（策略关闭 / 候选不足 / 匿名）。
  final List<FeedObjectCard> objectCards;
  final String? nextCursor;
  final String? previousCursor;
  final DateTime? paginationExpiresAt;

  /// 服务端权威下发的归因 id（frq_ 前缀）；端侧回显 + 透传行为事件。
  final String? feedRequestId;

  /// 本次推荐结果唯一的策略内容摘要（观测 / AB 归因）。
  final String? policyDigest;

  /// 远端失败后回退到本地快照时保留原始失败；null 表示本次不是缓存兜底。
  final Object? cacheFallbackError;

  /// 兜底快照距今毫秒数，仅用于页面生命周期埋点。
  final int? cacheAgeMs;

  /// 本地快照先返回时，对应的同查询远端再验证结果。
  ///
  /// 该 Future 只存在于 App 内部缓存装配，不进入 HTTP/DTO wire。消费者应先展示
  /// 当前页，再在仍属于同一 request generation 时采纳结果；失败结果会保留快照并
  /// 通过 [cacheFallbackError] 暴露真实错误，避免后台 Future 形成未处理异常。
  final Future<DiscoveryFeedPage>? revalidation;

  bool get isCacheFallback => cacheFallbackError != null;

  bool get isCanonicalEmpty =>
      items.isEmpty &&
      outcome == ContentFeedOutcome.empty &&
      emptyReason != null;

  bool get isStaleWhileRevalidate => revalidation != null;
}
