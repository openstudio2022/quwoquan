// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    super.key,
    required this.moreButtonKey,
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.shareCount,
    required this.commentCount,
    required this.likeCtrl,
    required this.onLike,
    required this.onComment,
    required this.onShare,
    required this.onMore,
  });

  final Key moreButtonKey;
  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final int shareCount;
  final int commentCount;
  final AnimationController likeCtrl;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onShare;
  final VoidCallback onMore;

  @override
  Widget build(BuildContext context) {
    final actionIconColor = AppColors.feedActionIcon(context);
    final likeColor = isLiked ? AppColors.worksLike : actionIconColor;

    final likeScale = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.0,
          end: 1.25,
        ).chain(CurveTween(curve: Curves.easeOut)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.25,
          end: 1.0,
        ).chain(CurveTween(curve: Curves.easeIn)),
        weight: 50,
      ),
    ]).animate(likeCtrl);

    return Row(
      children: [
        Expanded(
          child: _chip(
            context: context,
            selected: isLiked,
            semanticsLabel: UITextConstants.like,
            child: ScaleTransition(
              scale: likeScale,
              child: AppMediaHeartIcon(
                size: _feedToolbarIconSize,
                color: likeColor,
                filled: isLiked,
              ),
            ),
            label: formatCompactActionCount(likeCount),
            muted: actionIconColor,
            onTap: onLike,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            semanticsLabel: UITextConstants.share,
            child: AppMediaShareIcon(
              size: _feedToolbarIconSize,
              color: actionIconColor,
            ),
            label: formatCompactActionCount(shareCount),
            muted: actionIconColor,
            onTap: onShare,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            semanticsLabel: UITextConstants.comment,
            child: AppMediaCommentIcon(
              size: _feedToolbarIconSize,
              color: actionIconColor,
            ),
            label: formatCompactActionCount(commentCount),
            muted: actionIconColor,
            onTap: onComment,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            buttonKey: moreButtonKey,
            semanticsLabel: UITextConstants.more,
            child: Icon(
              Icons.more_horiz_rounded,
              size: _feedToolbarIconSize,
              color: actionIconColor,
            ),
            label: UITextConstants.more,
            muted: actionIconColor,
            onTap: onMore,
          ),
        ),
      ],
    );
  }

  Widget _chip({
    required BuildContext context,
    required Widget child,
    required String label,
    required Color muted,
    required VoidCallback onTap,
    Key? buttonKey,
    String? semanticsLabel,
    bool selected = false,
  }) {
    final foreground = selected ? AppColors.worksLike : muted;

    return CupertinoButton(
      key: buttonKey,
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Semantics(
        button: true,
        label: semanticsLabel,
        child: Container(
          height: AppSpacing.buttonHeightMdCompact,
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              child,
              SizedBox(width: AppSpacing.intraGroupXs),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.fade,
                softWrap: false,
                style: TextStyle(
                  fontSize: AppTypography.feedActionCountResponsive(context),
                  color: foreground,
                  fontWeight: AppTypography.regular,
                  height: AppSpacing.one,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeFeedMoreButton extends StatelessWidget {
  const _HomeFeedMoreButton({
    required this.isDark,
    required this.color,
    required this.onPressed,
  });

  final bool isDark;
  final Color color;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onPressed,
      child: SizedBox(
        width: AppSpacing.iconMedium,
        height: AppSpacing.iconMedium,
        child: Center(
          child: Icon(
            Icons.more_horiz_rounded,
            size: AppSpacing.twenty,
            color: color.withValues(alpha: isDark ? 0.8 : 0.68),
          ),
        ),
      ),
    );
  }
}

/// 上报 feed 卡片是否处于已挂载（视口 + cacheExtent 内）状态。
///
/// 卡片随滚动进入/离开构建集合时触发 `initState/dispose`，作为「正在阅读 / 视口内」
/// 的代理信号写入 [FeedRealtimePatchNotifier]；负反馈剔除据此只移除视口之外的项，
/// 保证不打断阅读位置（不抽走可见卡片、不引发滚动跳动）。
class _FeedPatchVisibilityReporter extends ConsumerStatefulWidget {
  const _FeedPatchVisibilityReporter({
    super.key,
    required this.postId,
    required this.child,
  });

  final String postId;
  final Widget child;

  @override
  ConsumerState<_FeedPatchVisibilityReporter> createState() =>
      _FeedPatchVisibilityReporterState();
}

class _FeedPatchVisibilityReporterState
    extends ConsumerState<_FeedPatchVisibilityReporter> {
  // 在 initState 捕获 notifier，dispose 时复用捕获引用（不在 dispose 读 ref）。
  FeedRealtimePatchNotifier? _patchNotifier;

  @override
  void initState() {
    super.initState();
    _patchNotifier = ref.read(feedRealtimePatchProvider.notifier);
    _patchNotifier?.setPostMounted(widget.postId, mounted: true);
  }

  @override
  void didUpdateWidget(covariant _FeedPatchVisibilityReporter oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 列表项移除后下标对应的 postId 可能改变：同步迁移挂载标记。
    if (oldWidget.postId != widget.postId) {
      _patchNotifier?.setPostMounted(oldWidget.postId, mounted: false);
      _patchNotifier?.setPostMounted(widget.postId, mounted: true);
    }
  }

  @override
  void dispose() {
    _patchNotifier?.setPostMounted(widget.postId, mounted: false);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// 首页推荐「有更新 / N 条新内容」轻量入口（顶部浮层 pill）。
///
/// 仅在该 channel 有实时 patch 提示（`new_candidate_hint` / `refresh_suggestion`）
/// 时出现；点击触发用户主动刷新。视觉走语义 token，尊重系统「减少动态效果」。
class _FeedRealtimeUpdatePill extends ConsumerWidget {
  const _FeedRealtimeUpdatePill({
    required this.channelId,
    required this.onRefresh,
  });

  final String channelId;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final hint = ref.watch(feedRealtimePatchHintProvider(channelId));
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    final Widget child;
    if (hint == null || !hint.hasUpdate) {
      child = const SizedBox.shrink();
    } else {
      final label = hint.newCandidateCount > 0
          ? DiscoveryFeedText.feedRealtimeNewContentBadge(hint.newCandidateCount)
          : DiscoveryFeedText.feedRealtimeUpdateHint;
      child = _buildPill(label);
    }

    if (reduceMotion) {
      return child;
    }
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 200),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (widget, animation) => FadeTransition(
        opacity: animation,
        child: SizeTransition(
          sizeFactor: animation,
          child: widget,
        ),
      ),
      child: child,
    );
  }

  Widget _buildPill(String label) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      color: AppColors.primaryColor,
      borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
      minimumSize: Size.zero,
      onPressed: onRefresh,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            CupertinoIcons.arrow_2_circlepath,
            size: AppSpacing.iconSmall,
            color: AppColors.white,
          ),
          SizedBox(width: AppSpacing.xs),
          Text(
            label,
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ],
      ),
    );
  }
}
