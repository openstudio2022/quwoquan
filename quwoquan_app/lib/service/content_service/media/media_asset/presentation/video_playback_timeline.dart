import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 同一套时间轴在内容流和 WorkBrowser 中的交互边界。
enum VideoPlaybackTimelineProfile { inlineFeed, workBrowser }

/// 时间轴视觉层级；尺寸与透明度只能从该语义层级解析。
enum VideoTimelineVisualLevel { normal, paused, scrubbing, ended }

typedef VideoTimelinePreviewBuilder = Widget? Function(
  BuildContext context,
  VideoPlaybackSnapshot snapshot,
  Duration target,
);

String formatVideoPlaybackDuration(Duration duration) {
  final totalSeconds = duration.inSeconds.clamp(0, 359999);
  final hours = totalSeconds ~/ 3600;
  final minutes = (totalSeconds % 3600) ~/ 60;
  final seconds = totalSeconds % 60;
  if (hours > 0) {
    return '$hours:${minutes.toString().padLeft(2, '0')}:'
        '${seconds.toString().padLeft(2, '0')}';
  }
  return '$minutes:${seconds.toString().padLeft(2, '0')}';
}

@immutable
final class VideoTimelineVisualTokens {
  const VideoTimelineVisualTokens._({
    required this.trackHeight,
    required this.handleSize,
    required this.trackAlpha,
    required this.progressAlpha,
  });

  static const longVideoThreshold = Duration(milliseconds: 30000);

  factory VideoTimelineVisualTokens.resolve(
    VideoTimelineVisualLevel level, {
    bool mutedWorkVideo = false,
  }) {
    if (level == VideoTimelineVisualLevel.ended) {
      return const VideoTimelineVisualTokens._(
        trackHeight: AppSpacing.xs,
        handleSize: AppSpacing.sm,
        trackAlpha: 0.46,
        progressAlpha: 1,
      );
    }
    if (mutedWorkVideo) {
      return level == VideoTimelineVisualLevel.scrubbing
          ? const VideoTimelineVisualTokens._(
              trackHeight: AppSpacing.sm,
              handleSize: AppSpacing.md,
              trackAlpha: 0.52,
              progressAlpha: 1,
            )
          : const VideoTimelineVisualTokens._(
              trackHeight: AppSpacing.two,
              handleSize: AppSpacing.zero,
              trackAlpha: 0.20,
              progressAlpha: 0.38,
            );
    }
    return switch (level) {
      VideoTimelineVisualLevel.normal => const VideoTimelineVisualTokens._(
        trackHeight: AppSpacing.two,
        handleSize: AppSpacing.zero,
        trackAlpha: 0.30,
        progressAlpha: 0.86,
      ),
      VideoTimelineVisualLevel.paused => const VideoTimelineVisualTokens._(
        trackHeight: AppSpacing.xs,
        handleSize: AppSpacing.sm,
        trackAlpha: 0.46,
        progressAlpha: 1,
      ),
      VideoTimelineVisualLevel.scrubbing => const VideoTimelineVisualTokens._(
        trackHeight: AppSpacing.six,
        handleSize: AppSpacing.interGroupSm,
        trackAlpha: 0.52,
        progressAlpha: 1,
      ),
      VideoTimelineVisualLevel.ended => throw StateError(
        'ended tokens are resolved before profile-specific tokens',
      ),
    };
  }

  final double trackHeight;
  final double handleSize;
  final double trackAlpha;
  final double progressAlpha;
}

/// 长作品拖动时只隐藏 chrome 投影，保留测量尺寸与子树状态。
/// 所有 slot 消费宿主同一快照，不创建局部计时器或播放状态。
class VideoPlaybackChromeVisibility extends StatelessWidget {
  const VideoPlaybackChromeVisibility({
    required this.snapshot,
    required this.child,
    super.key,
  });

  final VideoPlaybackSnapshot snapshot;
  final Widget child;

  @override
  Widget build(BuildContext context) => Visibility(
    visible: !snapshot.isScrubbing,
    maintainState: true,
    maintainAnimation: true,
    maintainSize: true,
    child: child,
  );
}

/// 共享视频时间轴。
///
/// 组件只消费 [VideoPlaybackSnapshot] 并向 [VideoPlaybackSession] 发命令，
/// 不持有或直接访问原生 controller。内容流使用被动 profile，WorkBrowser
/// 使用可拖动 profile。
class VideoPlaybackTimeline extends StatefulWidget {
  const VideoPlaybackTimeline({
    required this.session,
    required this.profile,
    this.previewBuilder,
    this.showDuration = true,
    this.showScrubTime = true,
    this.showVisuals = true,
    this.externallyControlledVisibility = false,
    this.isActive = true,
    this.durationKey,
    this.scrubTimeKey,
    super.key,
  });

  final VideoPlaybackSession session;
  final VideoPlaybackTimelineProfile profile;
  final VideoTimelinePreviewBuilder? previewBuilder;
  final bool showDuration;
  final bool showScrubTime;
  final bool showVisuals;

  /// 横向查看器统一持有显隐计时；时间轴不得再启动局部五秒窗口。
  final bool externallyControlledVisibility;
  final bool isActive;
  final Key? durationKey;
  final Key? scrubTimeKey;

  bool get interactive =>
      isActive && profile == VideoPlaybackTimelineProfile.workBrowser;

  @override
  State<VideoPlaybackTimeline> createState() => _VideoPlaybackTimelineState();
}

class _VideoPlaybackTimelineState extends State<VideoPlaybackTimeline> {
  static const Duration _keyboardSeekStep = Duration(seconds: 10);
  bool _gestureScrubbing = false;
  bool _interactionVisible = false;
  bool _pointerHeld = false;
  Offset? _pointerOrigin;
  bool _verticalIntent = false;
  Timer? _idleTimer;
  int _interactionGeneration = 0;
  final _sessionRevision = ValueNotifier<int>(0);
  bool _sessionRefreshScheduled = false;

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_sessionChanged);
  }

  void _sessionChanged() {
    if (_sessionRefreshScheduled) return;
    _sessionRefreshScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _sessionRefreshScheduled = false;
      if (mounted) _sessionRevision.value++;
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _reveal() {
    if (!widget.interactive) return;
    _idleTimer?.cancel();
    _interactionGeneration++;
    if (!_interactionVisible) setState(() => _interactionVisible = true);
  }

  void _scheduleHide() {
    _idleTimer?.cancel();
    if (widget.externallyControlledVisibility) return;
    final generation = ++_interactionGeneration;
    _idleTimer = Timer(const Duration(seconds: 5), () {
      if (!mounted ||
          generation != _interactionGeneration ||
          _pointerHeld ||
          _gestureScrubbing) {
        return;
      }
      setState(() => _interactionVisible = false);
    });
  }

  @override
  void didUpdateWidget(covariant VideoPlaybackTimeline oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.session, widget.session)) {
      oldWidget.session.removeListener(_sessionChanged);
      widget.session.addListener(_sessionChanged);
    }
    if (!identical(oldWidget.session, widget.session) ||
        oldWidget.profile != widget.profile ||
        oldWidget.externallyControlledVisibility !=
            widget.externallyControlledVisibility ||
        oldWidget.isActive != widget.isActive) {
      _idleTimer?.cancel();
      _interactionGeneration++;
      if (_gestureScrubbing) {
        unawaited(oldWidget.session.endScrub(commit: false));
      }
      _gestureScrubbing = false;
      _pointerHeld = false;
      _interactionVisible = false;
    }
  }

  @override
  void dispose() {
    _idleTimer?.cancel();
    _interactionGeneration++;
    widget.session.removeListener(_sessionChanged);
    _sessionRevision.dispose();
    if (_gestureScrubbing) unawaited(widget.session.endScrub(commit: false));
    super.dispose();
  }

  VideoTimelineVisualLevel _visualLevel(VideoPlaybackSnapshot snapshot) {
    if (snapshot.isScrubbing) {
      return VideoTimelineVisualLevel.scrubbing;
    }
    if (snapshot.isEnded) {
      return VideoTimelineVisualLevel.ended;
    }
    if (!snapshot.isPlaying) {
      return VideoTimelineVisualLevel.paused;
    }
    return VideoTimelineVisualLevel.normal;
  }

  void _startScrub(double dx, double width) {
    if (!widget.interactive ||
        width <= 0 ||
        _gestureScrubbing ||
        _verticalIntent ||
        !widget.session.snapshot.canSeek) {
      return;
    }
    _reveal();
    _gestureScrubbing = true;
    unawaited(widget.session.beginScrub());
    _updateTarget(dx, width);
  }

  void _updateTarget(double dx, double width) {
    final snapshot = widget.session.snapshot;
    if (!_gestureScrubbing ||
        width <= 0 ||
        snapshot.duration <= Duration.zero) {
      return;
    }
    final fraction = (dx / width).clamp(0.0, 1.0);
    widget.session.updateScrubTarget(
      Duration(
        milliseconds: (snapshot.duration.inMilliseconds * fraction).round(),
      ),
    );
  }

  void _finishScrub({required bool commit}) {
    if (!_gestureScrubbing) {
      return;
    }
    _gestureScrubbing = false;
    unawaited(widget.session.endScrub(commit: commit));
    _scheduleHide();
  }

  KeyEventResult _handleKeyEvent(FocusNode _, KeyEvent event) {
    if (!widget.interactive ||
        event is! KeyDownEvent ||
        !widget.session.snapshot.canSeek) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.arrowLeft ||
        key == LogicalKeyboardKey.arrowRight) {
      _reveal();
      _scheduleHide();
    }
    if (key == LogicalKeyboardKey.arrowLeft) {
      unawaited(widget.session.seekRelative(-_keyboardSeekStep));
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowRight) {
      unawaited(widget.session.seekRelative(_keyboardSeekStep));
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _sessionRevision,
      builder: (context, _) {
        final snapshot = widget.session.snapshot;
        if (snapshot.duration <= Duration.zero && !widget.interactive) {
          return const SizedBox.shrink();
        }
        return KeyedSubtree(
          key: ValueKey<String>(
            'video-playback-timeline-${widget.profile.name}',
          ),
          child: IgnorePointer(
            ignoring: !widget.interactive,
            child: _buildSemanticTimeline(context, snapshot),
          ),
        );
      },
    );
  }

  Widget _buildSemanticTimeline(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
  ) {
    final current = snapshot.effectivePosition;
    final currentText = formatVideoPlaybackDuration(current);
    final durationText = formatVideoPlaybackDuration(snapshot.duration);
    final semanticsValue = '$currentText / $durationText';
    final child = widget.showVisuals || widget.interactive
        ? LayoutBuilder(
            builder: (context, constraints) =>
                _buildTimeline(context, snapshot, constraints.maxWidth),
          )
        : const SizedBox.shrink();
    if (!widget.interactive) {
      return Semantics(
        label: MediaText.videoPlaybackProgressLabel,
        value: semanticsValue,
        readOnly: true,
        child: child,
      );
    }
    return Focus(
      canRequestFocus: snapshot.canSeek,
      onKeyEvent: _handleKeyEvent,
      child: Semantics(
        label: MediaText.videoPlaybackProgressLabel,
        hint: MediaText.videoPlaybackProgressHint,
        value: semanticsValue,
        increasedValue: formatVideoPlaybackDuration(
          snapshot.duration < current + _keyboardSeekStep
              ? snapshot.duration
              : current + _keyboardSeekStep,
        ),
        decreasedValue: formatVideoPlaybackDuration(
          current < _keyboardSeekStep
              ? Duration.zero
              : current - _keyboardSeekStep,
        ),
        enabled: snapshot.canSeek,
        focusable: snapshot.canSeek,
        onIncrease: snapshot.canSeek
            ? () => unawaited(widget.session.seekRelative(_keyboardSeekStep))
            : null,
        onDecrease: snapshot.canSeek
            ? () => unawaited(widget.session.seekRelative(-_keyboardSeekStep))
            : null,
        child: child,
      ),
    );
  }

  Widget _buildTimeline(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
    double width,
  ) {
    return switch (widget.profile) {
      VideoPlaybackTimelineProfile.inlineFeed => _buildInlineTimeline(
        context,
        snapshot,
        width,
      ),
      VideoPlaybackTimelineProfile.workBrowser => _buildWorkBrowserTimeline(
        context,
        snapshot,
      ),
    };
  }

  Widget _buildInlineTimeline(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
    double width,
  ) {
    final level = _visualLevel(snapshot);
    final tokens = VideoTimelineVisualTokens.resolve(level);
    final visualExtent = _trackVisualExtent(tokens);
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _buildTrackSurface(context, snapshot, width, tokens),
          ),
          Positioned(
            right: 0,
            bottom: visualExtent + AppSpacing.xs,
            child: _buildDurationLabel(
              snapshot,
              stableKey: const ValueKey<String>('home-video-duration'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWorkBrowserTimeline(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
  ) {
    final level = snapshot.isScrubbing
        ? VideoTimelineVisualLevel.scrubbing
        : _interactionVisible
        ? _visualLevel(snapshot)
        : VideoTimelineVisualLevel.normal;
    final tokens = VideoTimelineVisualTokens.resolve(
      level,
      mutedWorkVideo: _isLongWorkVideo(snapshot),
    );
    final visualExtent = _trackVisualExtent(tokens);
    final scrubLabel = _buildScrubLabel(snapshot);
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          SizedBox(
            height: AppSpacing.minInteractiveSize,
            width: double.infinity,
            child: LayoutBuilder(
              builder: (context, constraints) {
                return _buildTrackHitArea(
                  context,
                  snapshot,
                  constraints.maxWidth,
                  tokens,
                );
              },
            ),
          ),
          if (widget.showDuration && snapshot.duration > Duration.zero)
            Positioned(
              right: 0,
              bottom: visualExtent + AppSpacing.xs,
              child: _buildDurationLabel(
                snapshot,
                stableKey: const ValueKey<String>(
                  'works-video-transient-duration',
                ),
              ),
            ),
          if (snapshot.isScrubbing)
            Positioned(
              left: 0,
              right: 0,
              bottom: AppSpacing.minInteractiveSize + AppSpacing.xs,
              child: Center(child: scrubLabel),
            ),
          if (snapshot.isScrubbing && widget.previewBuilder != null)
            Positioned(
              left: 0,
              right: 0,
              bottom:
                  AppSpacing.minInteractiveSize +
                  _scrubFontSize(snapshot) * AppSpacing.textLineHeightBody +
                  AppSpacing.interGroupSm,
              child:
                  widget.previewBuilder!(
                    context,
                    snapshot,
                    snapshot.effectivePosition,
                  ) ??
                  const SizedBox.shrink(),
            ),
        ],
      ),
    );
  }

  Widget _buildTrackHitArea(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
    double width,
    VideoTimelineVisualTokens tokens,
  ) {
    return Listener(
      onPointerDown: (event) {
        _pointerHeld = true;
        _pointerOrigin = event.localPosition;
        _verticalIntent = false;
        _reveal();
      },
      onPointerMove: (event) {
        final delta =
            event.localPosition - (_pointerOrigin ?? event.localPosition);
        if (!_gestureScrubbing &&
            delta.dy.abs() > AppSpacing.interGroupSm &&
            delta.dy.abs() > delta.dx.abs()) {
          _verticalIntent = true;
        }
      },
      onPointerUp: (_) {
        _pointerHeld = false;
        _scheduleHide();
      },
      onPointerCancel: (_) {
        _pointerHeld = false;
        _finishScrub(commit: false);
        _scheduleHide();
      },
      child: GestureDetector(
        key: const ValueKey<String>('video-playback-timeline-hit-area'),
        behavior: HitTestBehavior.opaque,
        onTapUp: widget.interactive
            ? (details) {
                _startScrub(details.localPosition.dx, width);
                _finishScrub(commit: true);
              }
            : null,
        onTapCancel: widget.interactive
            ? () => _finishScrub(commit: false)
            : null,
        onHorizontalDragStart: widget.interactive
            ? (details) => _startScrub(details.localPosition.dx, width)
            : null,
        onHorizontalDragUpdate: widget.interactive
            ? (details) => _updateTarget(details.localPosition.dx, width)
            : null,
        onHorizontalDragEnd: widget.interactive
            ? (_) => _finishScrub(commit: true)
            : null,
        onHorizontalDragCancel: widget.interactive
            ? () => _finishScrub(commit: false)
            : null,
        child: SizedBox(
          height: AppSpacing.minInteractiveSize,
          child: Align(
            alignment: Alignment.bottomCenter,
            child: widget.showVisuals
                ? Opacity(
                    key: const ValueKey('video-playback-timeline-visibility'),
                    opacity:
                        widget.externallyControlledVisibility ||
                            snapshot.duration >
                                VideoTimelineVisualTokens.longVideoThreshold ||
                            _interactionVisible ||
                            snapshot.isScrubbing
                        ? 1
                        : 0,
                    child: _buildTrackSurface(context, snapshot, width, tokens),
                  )
                : const SizedBox.shrink(),
          ),
        ),
      ),
    );
  }

  Widget _buildTrackSurface(
    BuildContext context,
    VideoPlaybackSnapshot snapshot,
    double width,
    VideoTimelineVisualTokens tokens,
  ) {
    final current = snapshot.effectivePosition;
    final progress = snapshot.duration <= Duration.zero
        ? 0.0
        : (current.inMilliseconds / snapshot.duration.inMilliseconds).clamp(
            0.0,
            1.0,
          );
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    final animationDuration = reduceMotion
        ? Duration.zero
        : const Duration(milliseconds: 180);
    final visualExtent = _trackVisualExtent(tokens);
    // visual extent 整体贴底；内部轨道、进度和 thumb 共用中心线。
    // token 增高时只向上占用既有 44pt 热区，不把整条轨迁到热区中心。
    const trackAlignment = Alignment.centerLeft;
    final showProgress = !_isLongWorkVideo(snapshot) || progress > 0;
    return SizedBox(
      width: width,
      height: visualExtent,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: trackAlignment,
        children: [
          AnimatedContainer(
            key: const ValueKey<String>('video-playback-timeline-track'),
            duration: animationDuration,
            height: tokens.trackHeight,
            decoration: BoxDecoration(
              color: AppColors.white.withValues(alpha: tokens.trackAlpha),
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
            ),
          ),
          if (showProgress)
            Align(
              alignment: trackAlignment,
              child: SizedBox(
                width: width * progress,
                child: AnimatedContainer(
                  key: const ValueKey<String>(
                    'video-playback-timeline-progress',
                  ),
                  duration: animationDuration,
                  height: tokens.trackHeight,
                  decoration: BoxDecoration(
                    color: AppColors.white.withValues(
                      alpha: tokens.progressAlpha,
                    ),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.circularBorderRadius,
                    ),
                  ),
                ),
              ),
            ),
          if (tokens.handleSize > 0 && (showProgress || snapshot.isScrubbing))
            Positioned(
              left: (width * progress - tokens.handleSize / AppSpacing.two)
                  .clamp(0.0, (width - tokens.handleSize).clamp(0.0, width)),
              top: (visualExtent - tokens.handleSize) / AppSpacing.two,
              child: AnimatedContainer(
                key: const ValueKey<String>('video-playback-timeline-handle'),
                duration: animationDuration,
                width: tokens.handleSize,
                height: tokens.handleSize,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.white,
                ),
              ),
            ),
        ],
      ),
    );
  }

  bool _isLongWorkVideo(VideoPlaybackSnapshot snapshot) =>
      widget.profile == VideoPlaybackTimelineProfile.workBrowser &&
      snapshot.duration > VideoTimelineVisualTokens.longVideoThreshold;

  double _scrubFontSize(VideoPlaybackSnapshot snapshot) =>
      _isLongWorkVideo(snapshot) ? AppTypography.lg : AppTypography.base;

  double _trackVisualExtent(VideoTimelineVisualTokens tokens) {
    return tokens.handleSize > tokens.trackHeight
        ? tokens.handleSize
        : tokens.trackHeight;
  }

  Widget _buildDurationLabel(
    VideoPlaybackSnapshot snapshot, {
    required Key stableKey,
  }) {
    // Keep a stable ValueKey for tests/observability even when the host
    // injects a GlobalKey for caption collision measurement.
    Widget label = Opacity(
      key: stableKey,
      opacity: widget.showDuration ? 1 : 0,
      child: Text(
        formatVideoPlaybackDuration(snapshot.duration),
        style: _durationStyle(scrubbing: false),
      ),
    );
    final collisionKey = widget.durationKey;
    if (collisionKey != null) {
      label = KeyedSubtree(key: collisionKey, child: label);
    }
    return ExcludeSemantics(child: label);
  }

  Widget _buildScrubLabel(VideoPlaybackSnapshot snapshot) {
    return ExcludeSemantics(
      child: Opacity(
        key:
            widget.scrubTimeKey ??
            const ValueKey<String>('video-playback-scrub-time-label'),
        opacity: widget.showScrubTime ? 1 : 0,
        child: Text(
          '${formatVideoPlaybackDuration(snapshot.effectivePosition)} / '
          '${formatVideoPlaybackDuration(snapshot.duration)}',
          style: _durationStyle(scrubbing: true)
              .copyWith(fontSize: _scrubFontSize(snapshot)),
        ),
      ),
    );
  }

  TextStyle _durationStyle({required bool scrubbing}) {
    return TextStyle(
      color: AppColors.white.withValues(alpha: 0.96),
      fontSize: scrubbing ? AppTypography.base : AppTypography.xs,
      fontWeight: AppTypography.semiBold,
      height: AppSpacing.textLineHeightBody,
      fontFeatures: const [FontFeature.tabularFigures()],
      shadows: <Shadow>[
        Shadow(
          color: AppColors.black.withValues(alpha: 0.38),
          blurRadius: AppSpacing.xs,
        ),
      ],
    );
  }
}

/// 内容 Post 的被动时间轴定位壳；视觉轨贴底，总时长常驻轨道右上方。
class InlineFeedPlaybackOverlay extends StatelessWidget {
  const InlineFeedPlaybackOverlay({required this.session, super.key});

  final VideoPlaybackSession session;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.intraGroupSm,
            AppSpacing.zero,
            AppSpacing.intraGroupSm,
            AppSpacing.zero,
          ),
          child: VideoPlaybackTimeline(
            session: session,
            profile: VideoPlaybackTimelineProfile.inlineFeed,
          ),
        ),
      ),
    );
  }
}
