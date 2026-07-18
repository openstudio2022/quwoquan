import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

/// 首页发现流强类型 envelope。
///
/// 承载分页 items + 服务端权威下发的归因上下文（feedRequestId / rankingVersion /
/// reasonVersion）。feedRequestId 由 content-service 在 GET /content/feed 生成并随
/// 响应下发；端侧只读、回显（分页）并透传后续行为事件，不再由端侧自造。
class DiscoveryFeedPage {
  const DiscoveryFeedPage({
    required this.items,
    this.nextCursor,
    this.feedRequestId,
    this.rankingVersion,
    this.reasonVersion,
    this.cacheFallbackError,
    this.cacheAgeMs,
  });

  final List<PostBaseDto> items;
  final String? nextCursor;

  /// 服务端权威下发的归因 id（frq_ 前缀）；端侧回显 + 透传行为事件。
  final String? feedRequestId;

  /// 本次结果的精排管线版本（观测 / AB 归因）。
  final String? rankingVersion;

  /// 本次结果的交集理由管线版本。
  final String? reasonVersion;

  /// 远端失败后回退到本地快照时保留原始失败；null 表示本次不是缓存兜底。
  final Object? cacheFallbackError;

  /// 兜底快照距今毫秒数，仅用于页面生命周期埋点。
  final int? cacheAgeMs;

  bool get isCacheFallback => cacheFallbackError != null;
}
