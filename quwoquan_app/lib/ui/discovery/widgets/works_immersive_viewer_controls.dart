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
    required this.sharedTimelineEnabled,
    required this.previewTrackDescriptor,
    required this.previewTrackQuery,
    required this.durationVisible,
    required this.scrubTimeVisible,
    required this.durationKey,
    required this.scrubTimeKey,
  });

  final VideoPlaybackSession? session;
  final bool sharedTimelineEnabled;
  final VideoPreviewTrackDescriptor? previewTrackDescriptor;
  final VideoPreviewTrackQuery previewTrackQuery;
  final bool durationVisible;
  final bool scrubTimeVisible;
  final Key durationKey;
  final Key scrubTimeKey;

  @override
  Widget build(BuildContext context) {
    final activeSession = session;
    if (activeSession == null) {
      return const SizedBox.shrink();
    }
    return AnimatedBuilder(
      animation: activeSession,
      builder: (context, _) {
        final snapshot = activeSession.snapshot;
        if (snapshot.duration <= Duration.zero) {
          return const SizedBox.shrink();
        }
        return VideoPlaybackTimeline(
          key: const ValueKey<String>('works-video-control-row'),
          session: activeSession,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showDuration: durationVisible,
          showScrubTime: scrubTimeVisible,
          showVisuals: sharedTimelineEnabled && snapshot.isInitialized,
          durationKey: durationKey,
          scrubTimeKey: scrubTimeKey,
          previewBuilder: previewTrackDescriptor == null
              ? null
              : (context, snapshot, target) {
                  return VideoTimelinePreview(
                    descriptor: previewTrackDescriptor!,
                    query: previewTrackQuery,
                    target: target,
                  );
                },
        );
      },
    );
  }
}

class _WorksVideoSeriesBadge extends StatelessWidget {
  const _WorksVideoSeriesBadge({
    required this.episodeCurrent,
    required this.episodeTotal,
  });

  final int episodeCurrent;
  final int episodeTotal;

  @override
  Widget build(BuildContext context) {
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
