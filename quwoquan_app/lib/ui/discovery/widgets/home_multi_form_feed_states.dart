// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

class _HomeFeedSkeleton extends StatefulWidget {
  const _HomeFeedSkeleton({required this.isDark});

  final bool isDark;

  @override
  State<_HomeFeedSkeleton> createState() => _HomeFeedSkeletonState();
}

class _HomeFeedSkeletonState extends State<_HomeFeedSkeleton>
    with SingleTickerProviderStateMixin {
  static const int _placeholderCardCount = 3;
  AnimationController? _pulse;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    if (reduceMotion) {
      _pulse?.dispose();
      _pulse = null;
      return;
    }
    _pulse ??=
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 900),
          )
          ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pageBackground = SettingsSemanticConstants.conversationSheetCardSurface(
      widget.isDark,
    );
    return ColoredBox(
      color: pageBackground,
      child: ListView.separated(
        key: const ValueKey('home-feed-skeleton'),
        padding: EdgeInsets.only(top: AppSpacing.md, bottom: AppSpacing.md),
        physics: const NeverScrollableScrollPhysics(),
        itemCount: _placeholderCardCount,
        separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.md),
        itemBuilder: (context, index) => _HomeFeedSkeletonCard(pulse: _pulse),
      ),
    );
  }
}

class _HomeFeedSkeletonCard extends StatelessWidget {
  const _HomeFeedSkeletonCard({required this.pulse});

  final Animation<double>? pulse;

  @override
  Widget build(BuildContext context) {
    final fill = AppColors.iosFill(context);

    Widget bar({double? width, double? height}) => Container(
      width: width,
      height: height ?? DiscoveryFeedSpacing.homeFeedSkeletonLineHeight,
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(DiscoveryFeedSpacing.homeFeedMediaCornerRadius),
      ),
    );

    final body = Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: AppSpacing.forty,
                height: AppSpacing.forty,
                decoration: BoxDecoration(color: fill, shape: BoxShape.circle),
              ),
              const SizedBox(width: AppSpacing.sm),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  bar(width: DiscoveryFeedSpacing.homeFeedSkeletonNameWidth),
                  const SizedBox(height: AppSpacing.xs),
                  bar(width: DiscoveryFeedSpacing.homeFeedSkeletonMetaWidth),
                ],
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          bar(),
          const SizedBox(height: AppSpacing.xs),
          bar(width: DiscoveryFeedSpacing.homeFeedSkeletonBodyWidth),
          const SizedBox(height: AppSpacing.md),
          AspectRatio(
            aspectRatio: DiscoveryFeedSpacing.homeFeedSkeletonMediaAspectRatio,
            child: Container(
              decoration: BoxDecoration(
                color: fill,
                borderRadius: BorderRadius.circular(
                  DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
                ),
              ),
            ),
          ),
        ],
      ),
    );

    final pulse = this.pulse;
    if (pulse == null) {
      return Opacity(
        opacity: DiscoveryFeedSpacing.homeFeedSkeletonShimmerMaxOpacity,
        child: body,
      );
    }
    return AnimatedBuilder(
      animation: pulse,
      builder: (context, child) {
        final opacity =
            DiscoveryFeedSpacing.homeFeedSkeletonShimmerMinOpacity +
            (DiscoveryFeedSpacing.homeFeedSkeletonShimmerMaxOpacity -
                    DiscoveryFeedSpacing.homeFeedSkeletonShimmerMinOpacity) *
                pulse.value;
        return Opacity(opacity: opacity, child: child);
      },
      child: body,
    );
  }
}

/// 任务 A · 空态：加载完成但无内容时的运营兜底文案 + 再试入口（不编造内容）。
class _HomeFeedEmptyState extends StatelessWidget {
  const _HomeFeedEmptyState({required this.isDark, required this.onRetry});

  final bool isDark;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final pageBackground = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final accent = AppColors.iosAccent(context);
    return ColoredBox(
      color: pageBackground,
      child: Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          child: Column(
            key: const ValueKey('home-feed-empty'),
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Container(
                width: AppSpacing.avatarUserLg,
                height: AppSpacing.avatarUserLg,
                decoration: BoxDecoration(
                  color: AppColors.iosFill(context),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  CupertinoIcons.sparkles,
                  size: AppSpacing.iconMedium,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              const SizedBox(height: AppSpacing.containerSm),
              Text(
                DiscoveryFeedText.homeFeedEmptyTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                DiscoveryFeedText.homeFeedEmptyDescription,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosTertiaryLabel(context),
                ),
              ),
              const SizedBox(height: AppSpacing.lg),
              CupertinoButton(
                key: const ValueKey('home-feed-empty-retry'),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg,
                  vertical: AppSpacing.sm,
                ),
                onPressed: onRetry,
                child: Semantics(
                  button: true,
                  label: UITextConstants.tryAgain,
                  child: Text(
                    UITextConstants.tryAgain,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: accent,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

