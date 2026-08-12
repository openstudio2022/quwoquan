// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

const double _feedToolbarIconSize = AppSpacing.twenty;

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
  final ContentPostViewData item;
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
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        _chip(
          context: context,
          selected: isLiked,
          semanticsLabel: FoundationText.like,
          alignment: Alignment.centerLeft,
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
        _chip(
          context: context,
          semanticsLabel: FoundationText.share,
          child: AppMediaShareIcon(
            size: _feedToolbarIconSize,
            color: actionIconColor,
          ),
          label: formatCompactActionCount(shareCount),
          muted: actionIconColor,
          onTap: onShare,
        ),
        _chip(
          context: context,
          semanticsLabel: FoundationText.comment,
          child: AppMediaCommentIcon(
            size: _feedToolbarIconSize,
            color: actionIconColor,
          ),
          label: formatCompactActionCount(commentCount),
          muted: actionIconColor,
          onTap: onComment,
        ),
        _chip(
          context: context,
          buttonKey: moreButtonKey,
          semanticsLabel: ChatText.more,
          iconOnly: true,
          alignment: Alignment.centerRight,
          child: Icon(
            Icons.more_horiz_rounded,
            size: _feedToolbarIconSize,
            color: actionIconColor,
          ),
          muted: actionIconColor,
          onTap: onMore,
        ),
      ],
    );
  }

  Widget _chip({
    required BuildContext context,
    required Widget child,
    required Color muted,
    required VoidCallback onTap,
    Key? buttonKey,
    String? semanticsLabel,
    String? label,
    bool iconOnly = false,
    bool selected = false,
    Alignment alignment = Alignment.center,
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
          alignment: alignment,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              child,
              if (!iconOnly && label != null) ...[
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

/// N0-4 七态曝光门控：真实视口可见性驱动 impressed（50% 面积 + 1s 停留）。
///
/// 此前首页卡片在 build 帧即以硬编码 fraction=1/1000ms 上报 impressed，列表
/// 预构建（cacheExtent 内未入视口）的内容被记真实曝光 → 曝光过滤拉黑 7 天 +
/// CTR 分母与训练样本污染。本组件周期采样卡片与视口的真实交叠：
///  - 可见比例 ≥50% 累计 ≥1s → 上报一次 impressed（qualified）；
///  - 曾部分可见但从未达标 → dispose 时上报一次弱可见 visible；
///  - 从未进入视口（纯预构建）→ 不产生任何曝光事件。
class _QualifiedImpressionGate extends StatefulWidget {
  const _QualifiedImpressionGate({
    super.key,
    required this.contentId,
    required this.onQualified,
    required this.onWeakVisible,
    required this.child,
  });

  final String contentId;
  final void Function(double visibleFraction, Duration visibleDuration)
  onQualified;
  final VoidCallback onWeakVisible;
  final Widget child;

  @override
  State<_QualifiedImpressionGate> createState() =>
      _QualifiedImpressionGateState();
}

class _QualifiedImpressionGateState extends State<_QualifiedImpressionGate> {
  static const double _qualifiedFraction = 0.5;
  static const Duration _qualifiedDuration = Duration(milliseconds: 1000);

  final HomeFeedImpressionSamplingClock _samplingClock =
      HomeFeedImpressionSamplingClock.shared;
  late final VoidCallback _samplingListener;
  Duration _visibleAccum = Duration.zero;
  double _peakFraction = 0;
  bool _everVisible = false;
  bool _reported = false;
  bool _isActive = true;

  @override
  void initState() {
    super.initState();
    _samplingListener = _sample;
    _samplingClock.addListener(_samplingListener);
  }

  @override
  void didUpdateWidget(covariant _QualifiedImpressionGate oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.contentId != widget.contentId) {
      _flushWeakVisibleIfNeeded(oldWidget.onWeakVisible);
      _visibleAccum = Duration.zero;
      _peakFraction = 0;
      _everVisible = false;
      _reported = false;
      _samplingClock.addListener(_samplingListener);
    }
  }

  @override
  void activate() {
    super.activate();
    _isActive = true;
    if (!_reported) {
      _samplingClock.addListener(_samplingListener);
    }
  }

  @override
  void deactivate() {
    // mounted 在 inactive element 上仍为 true；必须在 deactivate 边界撤销采样，
    // 否则共享 Timer 会对已离开 render tree 的 context 调 findRenderObject。
    _isActive = false;
    _samplingClock.removeListener(_samplingListener);
    super.deactivate();
  }

  @override
  void dispose() {
    _flushWeakVisibleIfNeeded(widget.onWeakVisible);
    _samplingClock.removeListener(_samplingListener);
    super.dispose();
  }

  void _flushWeakVisibleIfNeeded(VoidCallback onWeakVisible) {
    if (!_reported && _everVisible) {
      _reported = true;
      onWeakVisible();
    }
  }

  void _sample() {
    if (_reported || !_isActive || !mounted) {
      return;
    }
    final fraction = _viewportVisibleFraction();
    if (fraction <= 0) {
      // 离开视口即清零累计：impressed 要求连续停留而非碎片累加。
      _visibleAccum = Duration.zero;
      return;
    }
    _everVisible = true;
    if (fraction > _peakFraction) {
      _peakFraction = fraction;
    }
    if (fraction < _qualifiedFraction) {
      _visibleAccum = Duration.zero;
      return;
    }
    _visibleAccum += _samplingClock.interval;
    if (_visibleAccum >= _qualifiedDuration) {
      _reported = true;
      _samplingClock.removeListener(_samplingListener);
      widget.onQualified(fraction, _visibleAccum);
    }
  }

  /// 卡片自身 paint 区域与屏幕视口的交叠比例（0~1）。
  double _viewportVisibleFraction() {
    final renderObject = context.findRenderObject();
    if (renderObject is! RenderBox || !renderObject.attached) {
      return 0;
    }
    if (!renderObject.hasSize || renderObject.size.isEmpty) {
      return 0;
    }
    final topLeft = renderObject.localToGlobal(Offset.zero);
    final rect = topLeft & renderObject.size;
    final view = View.of(context);
    final screen = Offset.zero & (view.physicalSize / view.devicePixelRatio);
    final intersection = rect.intersect(screen);
    if (intersection.width <= 0 || intersection.height <= 0) {
      return 0;
    }
    final cardArea = rect.width * rect.height;
    if (cardArea <= 0) {
      return 0;
    }
    return (intersection.width * intersection.height) / cardArea;
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
          ? DiscoveryFeedText.feedRealtimeNewContentBadge(
              hint.newCandidateCount,
            )
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
        child: SizeTransition(sizeFactor: animation, child: widget),
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
