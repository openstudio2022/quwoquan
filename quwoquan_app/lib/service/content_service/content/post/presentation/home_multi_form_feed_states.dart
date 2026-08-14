// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

class _HomeFeedSkeleton extends StatelessWidget {
  const _HomeFeedSkeleton({required this.isDark});

  static const int _placeholderCardCount = 3;

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    return ColoredBox(
      color: pageBackground,
      child: AppSkeletonShimmer(
        child: ListView.separated(
          key: const ValueKey('home-feed-skeleton'),
          padding: EdgeInsets.only(top: AppSpacing.md, bottom: AppSpacing.md),
          physics: const NeverScrollableScrollPhysics(),
          itemCount: _placeholderCardCount,
          separatorBuilder: (_, _) => const SizedBox(height: AppSpacing.md),
          itemBuilder: (context, index) => const _HomeFeedSkeletonCard(),
        ),
      ),
    );
  }
}

class _HomeFeedSkeletonCard extends StatelessWidget {
  const _HomeFeedSkeletonCard();

  @override
  Widget build(BuildContext context) {
    // 卡片形状：作者行（头像+名称/元信息）+ 两行正文 + 媒体位；
    // 脉动与占位视觉由统一 AppSkeleton primitives 承载。
    final cornerRadius = BorderRadius.circular(
      DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
    );

    Widget bar({double? width}) => AppSkeletonBlock(
      width: width,
      height: DiscoveryFeedSpacing.homeFeedSkeletonLineHeight,
      borderRadius: cornerRadius,
    );

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const AppSkeletonCircle(size: AppSpacing.forty),
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
            child: AppSkeletonBlock(borderRadius: cornerRadius),
          ),
        ],
      ),
    );
  }
}

/// 关注频道加载成功但尚无动态时的正常空态。
///
/// 反馈层统一走 `AppEmptyState`（feed 内嵌形态：无图标、融入内容流）；
/// 外层保留 `AppTerminalViewport` 承载整屏终态视口语义。
class _HomeFollowingFeedEmptyState extends StatelessWidget {
  const _HomeFollowingFeedEmptyState({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final pageBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    return ColoredBox(
      color: pageBackground,
      child: AppTerminalViewport(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.containerMd,
        ),
        child: const AppEmptyState(
          key: ValueKey('home-following-feed-empty'),
          title: DiscoveryFeedText.followingFeedEmptyTitle,
          subtitle: DiscoveryFeedText.followingFeedEmptyDescription,
        ),
      ),
    );
  }
}

/// Remote 查询健康完成但当前没有可展示内容时的中性终态。
///
/// 按规格条款这是「完成态小字」而非业务空态（内容区只显示次级灰色小字
/// 「内容加载完毕」，不并入统一空态组件），类名与语义保持一致。
class _HomeFeedCompletedNotice extends StatelessWidget {
  const _HomeFeedCompletedNotice({required this.isDark});

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
    return ColoredBox(
      color: pageBackground,
      child: AppTerminalViewport(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: AppEmptyState(
          key: const ValueKey<String>('home-feed-no-active-release'),
          title: SearchText.recoveryContentUnavailableTitle,
          subtitle: SearchText.recoveryContentUnavailableMessage,
          actionLabel: SearchText.reload,
          actionKey: const ValueKey<String>('home-feed-no-active-release-retry'),
          onAction: onRetry,
        ),
      ),
    );
  }
}
