part of 'works_immersive_viewer.dart';

class _WorksPageIndicator extends StatelessWidget {
  const _WorksPageIndicator({required this.total, required this.current});

  final int total;
  final int current;
  static const int _maxVisibleDots = 6;

  @override
  Widget build(BuildContext context) {
    final currentIndex = (current - 1).clamp(0, total - 1).toInt();
    final visibleCount = total.clamp(1, _maxVisibleDots).toInt();
    final windowStart = total <= _maxVisibleDots
        ? 0
        : (currentIndex - 2).clamp(0, total - visibleCount).toInt();
    final indicator = Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(visibleCount, (visibleIndex) {
        final absoluteIndex = windowStart + visibleIndex;
        final selected = absoluteIndex == currentIndex;
        final hasLeadingOverflow = windowStart > 0 && visibleIndex == 0;
        final hasTrailingOverflow =
            windowStart + visibleCount < total &&
            visibleIndex == visibleCount - 1;
        final alpha = selected
            ? 0.94
            : (absoluteIndex < currentIndex && hasLeadingOverflow) ||
                  (absoluteIndex > currentIndex && hasTrailingOverflow)
            ? 0.18
            : 0.38;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: 1.5),
          width: AppSpacing.xs + AppSpacing.hairline,
          height: AppSpacing.xs + AppSpacing.hairline,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.white.withValues(alpha: alpha),
          ),
        );
      }),
    );
    return IgnorePointer(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: DecoratedBox(
            key: const ValueKey<String>('works-page-indicator'),
            decoration: BoxDecoration(
              color: AppColors.black.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
              border: Border.all(
                color: AppColors.white.withValues(alpha: 0.06),
                width: AppSpacing.hairline,
              ),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: indicator,
            ),
          ),
        ),
      ),
    );
  }
}

class _WorksVideoControlRow extends StatelessWidget {
  const _WorksVideoControlRow({
    super.key,
    required this.session,
    required this.episodeCurrent,
    required this.episodeTotal,
  });

  final VideoPlaybackSession? session;
  final int episodeCurrent;
  final int episodeTotal;

  static String _formatDuration(Duration duration) {
    final totalSeconds = duration.inSeconds.clamp(0, 359999);
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final activeSession = session;
    if (activeSession == null) {
      return episodeTotal > 1
          ? Align(alignment: Alignment.centerLeft, child: _episodeBadge())
          : const SizedBox.shrink();
    }
    return AnimatedBuilder(
      animation: activeSession,
      builder: (context, _) {
        final snapshot = activeSession.snapshot;
        if (!snapshot.isInitialized) {
          return episodeTotal > 1
              ? Align(alignment: Alignment.centerLeft, child: _episodeBadge())
              : const SizedBox.shrink();
        }
        return Column(
          key: const ValueKey<String>('works-video-control-row'),
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                GestureDetector(
                  key: const ValueKey<String>('works-video-play-toggle'),
                  behavior: HitTestBehavior.opaque,
                  onTap: () => unawaited(activeSession.toggle()),
                  child: Icon(
                    snapshot.isPlaying
                        ? CupertinoIcons.pause_fill
                        : CupertinoIcons.play_fill,
                    size: AppSpacing.iconMedium,
                    color: AppColors.white.withValues(alpha: 0.92),
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(child: _WorksVideoTimeline(session: activeSession)),
                if (snapshot.controlsVisibility ==
                    VideoPlaybackControlsVisibility.transient) ...[
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Text(
                    _formatDuration(snapshot.duration),
                    key: const ValueKey<String>(
                      'works-video-transient-duration',
                    ),
                    style: TextStyle(
                      color: AppColors.white.withValues(alpha: 0.78),
                      fontSize: AppTypography.xxs,
                      fontWeight: AppTypography.medium,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ],
            ),
            if (episodeTotal > 1) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              _episodeBadge(),
            ],
          ],
        );
      },
    );
  }

  Widget _episodeBadge() {
    return Container(
      key: const ValueKey<String>('works-video-series-badge'),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs / 2,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.28),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        border: Border.all(color: AppColors.white.withValues(alpha: 0.14)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            UITextConstants.videoSeriesProgress(episodeCurrent, episodeTotal),
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.88),
              fontSize: AppTypography.xxs,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Icon(
            CupertinoIcons.arrow_right_arrow_left,
            size: AppTypography.xxs,
            color: AppColors.white.withValues(alpha: 0.66),
          ),
        ],
      ),
    );
  }
}

class _WorksVideoTimeline extends StatefulWidget {
  const _WorksVideoTimeline({required this.session});

  final VideoPlaybackSession session;

  @override
  State<_WorksVideoTimeline> createState() => _WorksVideoTimelineState();
}

class _WorksVideoTimelineState extends State<_WorksVideoTimeline> {
  bool _scrubbing = false;

  void _startScrub(double dx, double width) {
    if (width <= 0 || _scrubbing) {
      return;
    }
    _scrubbing = true;
    unawaited(widget.session.beginScrub());
    _updateTarget(dx, width);
  }

  void _updateTarget(double dx, double width) {
    final duration = widget.session.snapshot.duration;
    if (width <= 0 || duration <= Duration.zero) {
      return;
    }
    final fraction = (dx / width).clamp(0.0, 1.0);
    widget.session.updateScrubTarget(
      Duration(milliseconds: (duration.inMilliseconds * fraction).round()),
    );
  }

  void _finishScrub({required bool commit}) {
    if (!_scrubbing) {
      return;
    }
    _scrubbing = false;
    unawaited(widget.session.endScrub(commit: commit));
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final snapshot = widget.session.snapshot;
        final displayPosition = snapshot.effectivePosition;
        final progress = snapshot.duration <= Duration.zero
            ? 0.0
            : (displayPosition.inMilliseconds /
                      snapshot.duration.inMilliseconds)
                  .clamp(0.0, 1.0);
        final expanded = snapshot.isScrubbing || !snapshot.isPlaying;
        final trackHeight = expanded
            ? AppSpacing.xs
            : AppSpacing.xs / AppSpacing.two;
        final handleSize = expanded
            ? AppSpacing.sm
            : AppSpacing.xs + AppSpacing.hairline;
        return GestureDetector(
          key: const ValueKey<String>('works-video-timeline'),
          behavior: HitTestBehavior.opaque,
          onTapDown: (details) => _startScrub(details.localPosition.dx, width),
          onTapUp: (_) => _finishScrub(commit: true),
          onTapCancel: () => _finishScrub(commit: false),
          onHorizontalDragStart: (details) =>
              _startScrub(details.localPosition.dx, width),
          onHorizontalDragUpdate: (details) =>
              _updateTarget(details.localPosition.dx, width),
          onHorizontalDragEnd: (_) => _finishScrub(commit: true),
          onHorizontalDragCancel: () => _finishScrub(commit: false),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (snapshot.isScrubbing)
                Padding(
                  padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
                  child: Text(
                    '${_WorksVideoControlRow._formatDuration(displayPosition)} / '
                    '${_WorksVideoControlRow._formatDuration(snapshot.duration)}',
                    key: const ValueKey<String>('works-video-scrub-time-label'),
                    style: TextStyle(
                      color: AppColors.white.withValues(alpha: 0.96),
                      fontSize: AppTypography.xxs,
                      fontWeight: AppTypography.semiBold,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
              SizedBox(
                height: AppSpacing.minInteractiveSize / AppSpacing.two,
                child: Center(
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Container(
                        height: trackHeight,
                        decoration: BoxDecoration(
                          color: AppColors.white.withValues(
                            alpha: expanded ? 0.44 : 0.24,
                          ),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.circularBorderRadius,
                          ),
                        ),
                      ),
                      FractionallySizedBox(
                        widthFactor: progress,
                        child: Container(
                          height: trackHeight,
                          decoration: BoxDecoration(
                            color: AppColors.white.withValues(
                              alpha: expanded ? 1 : 0.92,
                            ),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.circularBorderRadius,
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        left:
                            (width * progress) - (handleSize / AppSpacing.two),
                        top: (trackHeight - handleSize) / AppSpacing.two,
                        child: Container(
                          width: handleSize,
                          height: handleSize,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: AppColors.white.withValues(
                              alpha: expanded ? 1 : 0.88,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _WorksArticlePageChevron extends StatelessWidget {
  const _WorksArticlePageChevron({
    super.key,
    required this.icon,
    required this.enabled,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final bool enabled;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: enabled ? onTap : null,
      child: SizedBox(
        width: AppSpacing.minInteractiveSize / 2,
        height: AppSpacing.minInteractiveSize / 2,
        child: Center(
          child: Icon(
            icon,
            size: AppTypography.sm,
            color: color.withValues(alpha: enabled ? 1 : 0.32),
          ),
        ),
      ),
    );
  }
}

class _WorksIntersectionDetailSheet extends StatelessWidget {
  const _WorksIntersectionDetailSheet({
    required this.reasons,
    required this.contextObjectTarget,
    this.onAskAssistant,
  });

  final List<IntersectionReason> reasons;
  final IntersectionTarget contextObjectTarget;
  final VoidCallback? onAskAssistant;

  @override
  Widget build(BuildContext context) {
    final displayReasons = reasons
        .map(
          (reason) => displayReadyIntersectionReason(
            reason,
            contextObjectTarget: contextObjectTarget,
          ),
        )
        .whereType<IntersectionReason>()
        .toList(growable: false);
    return AppBottomModalSurface(
      onDismiss: () => Navigator.pop(context),
      panelKey: const ValueKey<String>('works-intersection-detail-sheet'),
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
              child: Text(
                DiscoveryFeedText.intersectionDetailTitle,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            for (var i = 0; i < displayReasons.length; i++) ...[
              if (i > 0) SizedBox(height: AppSpacing.intraGroupSm),
              _WorksIntersectionReasonRow(reason: displayReasons[i]),
            ],
            if (onAskAssistant != null) ...[
              SizedBox(height: AppSpacing.interGroupSm),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton(
                  key: const ValueKey<String>(
                    'works-intersection-ask-assistant-button',
                  ),
                  color: AppColors.iosAccent(context),
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupSm,
                    horizontal: AppSpacing.containerMd,
                  ),
                  onPressed: onAskAssistant,
                  child: Text(
                    UITextConstants.objectIntersectionCtaAskAssistant,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                      color: CupertinoColors.white,
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _WorksIntersectionReasonRow extends StatelessWidget {
  const _WorksIntersectionReasonRow({required this.reason});

  final IntersectionReason reason;

  @override
  Widget build(BuildContext context) {
    final primary = reason.primaryText.trim();
    final secondary = reason.secondaryText.trim();
    if (primary.isEmpty) {
      return const SizedBox.shrink();
    }
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            CupertinoIcons.checkmark_circle_fill,
            key: const ValueKey<String>('works-intersection-check'),
            size: AppSpacing.iconSmall,
            color: AppColors.worksAccent,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (primary.isNotEmpty)
                  Text(
                    primary,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                if (secondary.isNotEmpty) ...[
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Text(
                    secondary,
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColorsFunctional.getColor(
                        MediaQuery.platformBrightnessOf(context) ==
                            Brightness.dark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
