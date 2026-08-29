part of 'video_player_widget.dart';

/// Surface-specific playback chrome. It intentionally excludes command handling:
/// commands always go through [VideoPlaybackSession].
enum VideoPlaybackOverlayMode { none, inlineFeed }

/// 视频播放器组件
/// 继承自侵入式媒体浏览器，支持视频播放功能
/// 一条播放候选的取址与缓存身份。
///
/// 公开路由 [AdaptiveVideoDeliverySet] 从公开交付引用推导（可能含 HLS 升级），
/// 私有路由已校验的短签地址单候选给出；两路在此汇成同一形状，播放循环因此
/// 不需要知道当前是公开还是私有。
@immutable
class _PlaybackCandidate {
  const _PlaybackCandidate({required this.url, required this.cacheIdentity});

  final String url;
  final String cacheIdentity;
}


class VideoPlayerWidget extends ConsumerStatefulWidget {
  /// 已在 mapper/边界验证的公开媒体交付引用；播放器不再解析业务 object key。
  /// 私有交付时缺席，取址改由 [signedDelivery] 承担。
  final MediaDeliveryReference? deliveryReference;

  /// 私有短签播放交付。与 [deliveryReference] 互斥，恰有一个在场。
  final SignedVideoDelivery? signedDelivery;
  final MediaDeliveryReference? adaptiveDeliveryReference;
  final int adaptiveDescriptorVersion;
  /// 封面的 typed 交付绑定（DEC-033）：私有封面走短签路，公开封面走公开候选。
  /// 播放器不从 URL 形态推断交付形态，绑定由调用方按投影声明交出。
  final MediaDeliveryBinding thumbnailBinding;
  final bool initialize;
  final bool autoPlay;
  final bool showControls;
  final VoidCallback? onTap;
  final VoidCallback? onFullScreen;
  final VoidCallback? onExit;
  final Function(VideoPlayerController)? onControllerCreated;
  final VideoPlaybackSession? playbackSession;
  final ValueChanged<VideoPlaybackSession>? onPlaybackSessionCreated;
  final ValueChanged<VideoEffectivePlaybackEvidence>? onEffectivePlayback;
  final VideoPlaybackOverlayMode overlayMode;
  final Duration? verifiedDuration;
  final double? aspectRatio;
  final VideoViewType? viewType;

  /// 任务 B · 播放启动成功回调：startupLatency 为从初始化到可播放的耗时，
  /// candidateIndex 为命中的候选源序号（用于自动播放启动时延度量）。
  final void Function(Duration startupLatency, int candidateIndex)?
  onPlaybackStarted;

  /// 播放失败回调：只暴露确定性的脱敏失败结果。
  final void Function(MediaPlaybackFailure failure)? onPlaybackFailed;

  const VideoPlayerWidget({
    super.key,
    this.deliveryReference,
    this.signedDelivery,
    this.adaptiveDeliveryReference,
    this.adaptiveDescriptorVersion = 0,
    this.thumbnailBinding = const MediaDeliveryBinding.absent(),
    this.initialize = true,
    this.autoPlay = false,
    this.showControls = true,
    this.onTap,
    this.onFullScreen,
    this.onExit,
    this.onControllerCreated,
    this.playbackSession,
    this.onPlaybackSessionCreated,
    this.onEffectivePlayback,
    this.overlayMode = VideoPlaybackOverlayMode.none,
    this.verifiedDuration,
    this.aspectRatio,
    this.viewType,
    this.onPlaybackStarted,
    this.onPlaybackFailed,
  }) : assert(
         (deliveryReference == null) != (signedDelivery == null),
         '公开交付引用与私有短签交付恰有一个在场：两者都缺就没有取址，'
         '两者都在就有两条并行取址路径',
       );

  /// 本次播放的取址来源：私有路优先，两者互斥由构造断言保证。
  String get playbackUrl =>
      signedDelivery?.deliveryUri.toString() ?? deliveryReference!.url;

  /// 失败缓存与下载缓存的稳定身份；私有路不把签名 query 带进缓存键。
  String get playbackCacheIdentity =>
      signedDelivery?.cacheIdentity ?? deliveryReference!.cacheIdentity;

  @override
  ConsumerState<VideoPlayerWidget> createState() => _VideoPlayerWidgetState();

  /// 测试钩子：暴露当前并发控制器槽占用数。
  @visibleForTesting
  static int get debugActiveControllerCount =>
      _VideoPlayerWidgetState._activeControllerCount;

  @visibleForTesting
  static void debugResetControllerSlots() {
    _VideoPlayerWidgetState._activeControllerCount = 0;
  }
}
