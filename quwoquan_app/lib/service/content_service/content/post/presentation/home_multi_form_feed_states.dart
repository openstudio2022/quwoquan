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
    _pulse ??= AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(widget.isDark);
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
        borderRadius: BorderRadius.circular(
          DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
        ),
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

/// 关注频道加载成功但尚无动态时的正常空态。
class _HomeFollowingFeedEmptyState extends StatelessWidget {
  const _HomeFollowingFeedEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return ColoredBox(
      color: pageBackground,
      child: AppTerminalViewport(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.containerMd,
        ),
        child: Column(
          key: const ValueKey('home-following-feed-empty'),
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              DiscoveryFeedText.followingFeedEmptyTitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.semiBold,
                color: primaryText,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              DiscoveryFeedText.followingFeedEmptyDescription,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: secondaryText,
                height: AppSpacing.textLineHeightBody,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Remote 查询健康完成但当前没有可展示内容时的中性终态。
class _HomeFeedCompletedEmptyState extends StatelessWidget {
  const _HomeFeedCompletedEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return ColoredBox(
      color: pageBackground,
      child: AppTerminalViewport(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Text(
          DiscoveryFeedText.contentLoadingCompleted,
          key: const ValueKey<String>('home-feed-completed-empty'),
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosCaption1,
            color: secondaryText,
          ),
        ),
      ),
    );
  }
}

/// test_live 尚未绑定 active release 时的显式可恢复终态。
///
/// `no_active_release` 是服务端确认的 canonical empty，不是健康的“内容已加载完毕”；
/// 这里保留 unavailable 语义并允许用户在 release 激活后重试同一 Remote Query。
class _HomeFeedNoActiveReleaseState extends StatelessWidget {
  const _HomeFeedNoActiveReleaseState({
    required this.isDark,
    required this.onRetry,
  });

  final bool isDark;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return ColoredBox(
      color: pageBackground,
      child: AppTerminalViewport(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          key: const ValueKey<String>('home-feed-no-active-release'),
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              SearchText.recoveryContentUnavailableTitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: primaryText,
              ),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              SearchText.recoveryContentUnavailableMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: secondaryText,
                height: AppSpacing.textLineHeightBody,
              ),
            ),
            const SizedBox(height: AppSpacing.containerMd),
            CupertinoButton.filled(
              key: const ValueKey<String>('home-feed-no-active-release-retry'),
              onPressed: onRetry,
              child: const Text(SearchText.reload),
            ),
          ],
        ),
      ),
    );
  }
}
