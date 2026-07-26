part of 'video_player_widget.dart';

/// Surface-specific playback chrome. It intentionally excludes command handling:
/// commands always go through [VideoPlaybackSession].
enum VideoPlaybackOverlayMode { none, inlineFeed }

/// 视频播放器组件
/// 继承自侵入式媒体浏览器，支持视频播放功能
class VideoPlayerWidget extends ConsumerStatefulWidget {
  /// 已在 mapper/边界验证的公开媒体交付引用；播放器不再解析业务 object key。
  final MediaDeliveryReference deliveryReference;
  final MediaDeliveryReference? thumbnailReference;
  final bool initialize;
  final bool autoPlay;
  final bool showControls;
  final VoidCallback? onTap;
  final VoidCallback? onFullScreen;
  final Function(VideoPlayerController)? onControllerCreated;
  final VideoPlaybackSession? playbackSession;
  final ValueChanged<VideoPlaybackSession>? onPlaybackSessionCreated;
  final ValueChanged<VideoEffectivePlaybackEvidence>? onEffectivePlayback;
  final VideoPlaybackOverlayMode overlayMode;
  final Duration? verifiedDuration;
  final double? aspectRatio;

  /// 任务 B · 播放启动成功回调：startupLatency 为从初始化到可播放的耗时，
  /// candidateIndex 为命中的候选源序号（用于自动播放启动时延度量）。
  final void Function(Duration startupLatency, int candidateIndex)?
  onPlaybackStarted;

  /// 播放失败回调：只暴露确定性的脱敏失败结果。
  final void Function(MediaPlaybackFailure failure)? onPlaybackFailed;

  const VideoPlayerWidget({
    super.key,
    required this.deliveryReference,
    this.thumbnailReference,
    this.initialize = true,
    this.autoPlay = false,
    this.showControls = true,
    this.onTap,
    this.onFullScreen,
    this.onControllerCreated,
    this.playbackSession,
    this.onPlaybackSessionCreated,
    this.onEffectivePlayback,
    this.overlayMode = VideoPlaybackOverlayMode.none,
    this.verifiedDuration,
    this.aspectRatio,
    this.onPlaybackStarted,
    this.onPlaybackFailed,
  });

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
