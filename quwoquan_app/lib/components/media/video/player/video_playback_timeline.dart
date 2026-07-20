import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 同一套时间轴在内容流和 WorkBrowser 中的交互边界。
enum VideoPlaybackTimelineProfile { inlineFeed, workBrowser }

/// 时间轴视觉层级；尺寸与透明度只能从该语义层级解析。
enum VideoTimelineVisualLevel { normal, paused, scrubbing }

typedef VideoTimelinePreviewBuilder =
    Widget? Function(
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

  factory VideoTimelineVisualTokens.resolve(VideoTimelineVisualLevel level) {
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
    };
  }

  final double trackHeight;
  final double handleSize;
  final double trackAlpha;
  final double progressAlpha;
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
  final Key? durationKey;
  final Key? scrubTimeKey;

  bool get interactive => profile == VideoPlaybackTimelineProfile.workBrowser;

  @override
  State<VideoPlaybackTimeline> createState() => _VideoPlaybackTimelineState();
}

class _VideoPlaybackTimelineState extends State<VideoPlaybackTimeline> {
  static const Duration _keyboardSeekStep = Duration(seconds: 10);
  bool _gestureScrubbing = false;

  VideoTimelineVisualLevel _visualLevel(VideoPlaybackSnapshot snapshot) {
    if (snapshot.isScrubbing) {
      return VideoTimelineVisualLevel.scrubbing;
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
        !widget.session.snapshot.canSeek) {
      return;
    }
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
  }

  KeyEventResult _handleKeyEvent(FocusNode _, KeyEvent event) {
    if (!widget.interactive ||
        event is! KeyDownEvent ||
        !widget.session.snapshot.canSeek) {
      return KeyEventResult.ignored;
    }
    final key = event.logicalKey;
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
      animation: widget.session,
      builder: (context, _) {
        final snapshot = widget.session.snapshot;
        if (snapshot.duration <= Duration.zero) {
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
    final child = widget.showVisuals
        ? LayoutBuilder(
            builder: (context, constraints) =>
                _buildTimeline(context, snapshot, constraints.maxWidth),
          )
        : const SizedBox.shrink();
    if (!widget.interactive) {
      return Semantics(
        label: UITextConstants.videoPlaybackProgressLabel,
        value: semanticsValue,
        readOnly: true,
        child: child,
      );
    }
    return Focus(
      canRequestFocus: snapshot.canSeek,
      onKeyEvent: _handleKeyEvent,
      child: Semantics(
        label: UITextConstants.videoPlaybackProgressLabel,
        hint: UITextConstants.videoPlaybackProgressHint,
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
    final level = _visualLevel(snapshot);
    final tokens = VideoTimelineVisualTokens.resolve(level);
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
                  AppTypography.base * AppSpacing.textLineHeightBody +
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
    return GestureDetector(
      key: const ValueKey<String>('video-playback-timeline-hit-area'),
      behavior: HitTestBehavior.opaque,
      onTapDown: widget.interactive
          ? (details) => _startScrub(details.localPosition.dx, width)
          : null,
      onTapUp: widget.interactive ? (_) => _finishScrub(commit: true) : null,
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
          child: _buildTrackSurface(context, snapshot, width, tokens),
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
    return SizedBox(
      width: width,
      height: visualExtent,
      child: Stack(
        clipBehavior: Clip.none,
        alignment: Alignment.bottomLeft,
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
          Align(
            alignment: Alignment.bottomLeft,
            child: SizedBox(
              width: width * progress,
              child: AnimatedContainer(
                key: const ValueKey<String>('video-playback-timeline-progress'),
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
          if (tokens.handleSize > 0)
            Positioned(
              left: (width * progress - tokens.handleSize / AppSpacing.two)
                  .clamp(0.0, (width - tokens.handleSize).clamp(0.0, width)),
              bottom: 0,
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
          style: _durationStyle(scrubbing: true),
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
