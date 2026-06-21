import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 对象页吸顶模式（V3 三档，对应三壳范式）：
/// - [full]/[standard]：沉浸头图 + identity 吸顶 + 吸顶一级页签（profile/circle 同源）。
/// - [minimal]：仅 toolbar 单渐显，无吸顶页签 / 无 identity 吸顶（homepage 范式），可带底栏。
enum ObjectPagePinMode { full, standard, minimal }

/// 对象页统一壳层骨架（V3 合规共享层，单一几何真相源）。
///
/// 收口 ProfileShell / HomepageDetailShell / CircleShell 三壳的沉浸头图 + 下拉回弹 +
/// summary 高度测量 + 两段吸顶过渡（identity / 一级页签）+ 三槽 toolbar + 吸顶页签 overlay +
/// 最大宽度约束几何。业务差异通过 builder 插槽注入；不持有业务状态。
class ObjectPageShell extends StatefulWidget {
  const ObjectPageShell({
    super.key,
    required this.keyPrefix,
    required this.backgroundBuilder,
    required this.summaryBuilder,
    required this.toolbarBuilder,
    required this.tabBodyBuilder,
    this.tabBarBuilder,
    this.bottomBar,
    this.pinMode = ObjectPagePinMode.standard,
    this.baseHeightRatio,
    this.maxStretchHeightRatio,
    this.identityPinExtent = 0,
    this.cardRadius = AppSpacing.radiusTwenty,
    this.scrollController,
    this.onSwipe,
    this.cacheExtentScreens = 4,
    this.toolbarContentHeight,
    this.identityTransitionDistance,
    this.collapseCurve,
    this.enablePinnedTabOverlay = true,
    this.summaryTrackerKey,
    this.scrollViewKey,
    this.contentHorizontalPadding = 0,
    this.surfaceBridgeOverride,
    this.tabSurfaceBottomPadding,
    this.tabSurfaceHorizontalPadding = 0,
    this.tabSurfaceTopRadius = 0,
    this.scrollBackgroundWithContent = false,
  });

  /// ValueKey 前缀（测试探针稳定锚点，如 'circle-shell' / 'profile-shell' / 'homepage-shell'）。
  final String keyPrefix;

  /// 沉浸头图层：入参当前下拉偏移。
  final Widget Function(BuildContext context, double pullOffset)
  backgroundBuilder;

  /// summary 卡（头部 + 操作 + 交集卡），骨架自动测量其高度用于一级页签吸顶阈值。
  final WidgetBuilder summaryBuilder;

  /// 三槽 toolbar：入参 identity 吸顶进度、toolbar 背景不透明度。
  final Widget Function(
    BuildContext context,
    double identityProgress,
    double backgroundOpacity,
  )
  toolbarBuilder;

  /// tab 内容体。
  final WidgetBuilder tabBodyBuilder;

  /// 一级页签条：入参 pinned（是否吸顶态）、opacity（inline 渐隐）。
  /// minimal 模式可为 null（无一级页签）。
  final Widget Function(BuildContext context, bool pinned, double opacity)?
  tabBarBuilder;

  /// 底部固定操作栏（minimal/homepage 范式）；为空则无底栏。
  final Widget? bottomBar;

  final ObjectPagePinMode pinMode;
  final double? baseHeightRatio;
  final double? maxStretchHeightRatio;

  /// identity 吸顶阈值的额外延伸（如头像 outerDiameter - intrusion），用于 identity 渐显时机。
  final double identityPinExtent;
  final double cardRadius;
  final ScrollController? scrollController;

  /// 一级页签左右滑动切换（可选）；返回是否消费。
  final void Function(DragEndDetails details)? onSwipe;
  final double cacheExtentScreens;

  /// toolbar 内容高度（不含 safe inset）；为空用 appChromeTopBarHeight。
  /// profile 传自适应单行标题高度以匹配紧凑 toolbar。
  final double? toolbarContentHeight;

  /// identity 吸顶过渡距离；为空用默认 pin 过渡。
  /// profile 可传极短距离，避免大头像与 compact identity 长时间半透明混叠。
  final double? identityTransitionDistance;

  /// identity / 一级页签吸顶过渡曲线；为空用 easeOutCubic。
  final Curve? collapseCurve;

  /// 是否启用吸顶一级页签 overlay（profile 可按配置关闭）。
  final bool enablePinnedTabOverlay;

  /// summary 屏幕位置常驻探针 key（1px overlay，随滚动追踪 summary 计算位置，
  /// 即使 summary 卡滚出 viewport 仍在 tree）；用于壳层位置契约测试。
  final Key? summaryTrackerKey;

  /// 主 CustomScrollView 的 key（壳层契约测试探针，如 TestKeys.homepageDetailPage）。
  final Key? scrollViewKey;

  /// summary / tab surface 区块的水平外边距（homepage 范式用 containerMd；circle/profile 为 0）。
  final double contentHorizontalPadding;

  /// summary 与 tab surface 之间的桥接重叠量；为空用 cardRadius（圆角重叠）；homepage 传 0（无重叠）。
  final double? surfaceBridgeOverride;

  /// tab surface 底部内边距；为空用 viewPadding.bottom + interGroupLg。
  final double? tabSurfaceBottomPadding;

  /// 仅作用于 tab 内容 surface 的水平内缩，避免影响 summary 卡片几何。
  final double tabSurfaceHorizontalPadding;

  /// 仅作用于 tab 内容 surface 的顶部圆角；默认保持历史直边。
  final double tabSurfaceTopRadius;

  /// 上滑时让封面跟随内容向上离屏；下拉时仍保持顶边固定，只做现有拉伸/回弹。
  final bool scrollBackgroundWithContent;

  double get _surfaceBridge => surfaceBridgeOverride ?? cardRadius;

  /// 同源下拉回弹阻尼（三壳逐字相同）。
  static double springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) return 0;
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  @override
  State<ObjectPageShell> createState() => _ObjectPageShellState();
}

class _ObjectPageShellState extends State<ObjectPageShell> {
  late final ScrollController _scrollController;
  bool _ownsController = false;
  late final GlobalKey _summaryKey;

  double _scrollOffset = 0;
  double _rawPullOffset = 0;
  double _pullOffset = 0;
  double _summaryHeight = 0;

  @override
  void initState() {
    super.initState();
    _summaryKey = GlobalKey();
    _scrollController = widget.scrollController ?? ScrollController();
    _ownsController = widget.scrollController == null;
    _scrollController.addListener(_handleScrollOffset);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_handleScrollOffset);
    if (_ownsController) _scrollController.dispose();
    super.dispose();
  }

  void _handleScrollOffset() {
    if (!_scrollController.hasClients) return;
    final next = max(0.0, _scrollController.offset);
    if ((next - _scrollOffset).abs() < 0.5) return;
    setState(() => _scrollOffset = next);
  }

  double _baseHeightRatio(BuildContext context) =>
      widget.baseHeightRatio ??
      AppSpacing.adaptiveProfileHeaderBaseHeightRatio(context);
  double _maxStretchRatio(BuildContext context) =>
      widget.maxStretchHeightRatio ??
      AppSpacing.adaptiveProfileHeaderMaxStretchHeightRatio(context);

  double _baseBackgroundHeight(BuildContext context) =>
      MediaQuery.sizeOf(context).height * _baseHeightRatio(context);
  double _maxBackgroundHeight(BuildContext context) =>
      MediaQuery.sizeOf(context).height * _maxStretchRatio(context);

  double _currentBackgroundHeight(BuildContext context) {
    final base = _baseBackgroundHeight(context);
    return (base + _pullOffset).clamp(base, _maxBackgroundHeight(context));
  }

  double _backgroundSpacerHeight(BuildContext context) =>
      max(0.0, _currentBackgroundHeight(context) - _rawPullOffset);

  double _backgroundTop() =>
      widget.scrollBackgroundWithContent ? -_scrollOffset : 0.0;

  double _toolbarHeight(BuildContext context) =>
      AppSpacing.appChromeTopSafeInset(
        MediaQuery.viewPaddingOf(context).top,
        context,
      ) +
      (widget.toolbarContentHeight ??
          AppSpacing.appChromeTopBarHeight(context));

  double _pinTransitionDistance() => max(AppSpacing.buttonHeight, 32.0);

  double _summaryTopAtRest(BuildContext context) =>
      _baseBackgroundHeight(context);
  double _primaryTabTopAtRest(BuildContext context) =>
      _summaryTopAtRest(context) + _summaryHeight;

  double _curve(double value) => (widget.collapseCurve ?? Curves.easeOutCubic)
      .transform(value.clamp(0.0, 1.0));

  double _identityPinnedProgress(BuildContext context) {
    if (widget.pinMode == ObjectPagePinMode.minimal) {
      // 极简：toolbar 跟随滚动单渐显（无 identity 概念）。
      final trigger = max(
        1.0,
        _baseBackgroundHeight(context) - _toolbarHeight(context),
      );
      return _curve(_scrollOffset / trigger);
    }
    final pinBottom = _baseBackgroundHeight(context) + widget.identityPinExtent;
    final threshold = max(0.0, pinBottom - _toolbarHeight(context));
    final distance = max(
      widget.identityTransitionDistance ?? _pinTransitionDistance(),
      1.0,
    );
    return _curve((_scrollOffset - threshold) / distance);
  }

  double _primaryTabPinnedProgress(BuildContext context) {
    if (widget.tabBarBuilder == null) return 0;
    final threshold = max(
      0.0,
      _primaryTabTopAtRest(context) - _toolbarHeight(context),
    );
    return _curve((_scrollOffset - threshold) / _pinTransitionDistance());
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) return false;
    if (notification is ScrollUpdateNotification ||
        notification is OverscrollNotification ||
        notification is ScrollEndNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final nextRaw = -pixels;
        final maxPull =
            _maxBackgroundHeight(context) - _baseBackgroundHeight(context);
        final nextPull = ObjectPageShell.springDampedOffset(nextRaw, maxPull);
        if ((nextRaw - _rawPullOffset).abs() < 0.5 &&
            (nextPull - _pullOffset).abs() < 0.5) {
          return false;
        }
        setState(() {
          _rawPullOffset = nextRaw;
          _pullOffset = nextPull;
        });
      } else if (_rawPullOffset != 0 || _pullOffset != 0) {
        setState(() {
          _rawPullOffset = 0;
          _pullOffset = 0;
        });
      }
    }
    return false;
  }

  void _scheduleSummaryMeasure() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final height = _summaryKey.currentContext?.size?.height ?? 0;
      if ((height - _summaryHeight).abs() < 0.5) return;
      setState(() => _summaryHeight = height);
    });
  }

  Widget _constrain(Widget child, {double? horizontalPadding}) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = AppSpacing.adaptiveFeedMaxContentWidth(
          constraints.maxWidth,
        );
        final resolvedPadding =
            horizontalPadding ?? widget.contentHorizontalPadding;
        final padded = resolvedPadding > 0
            ? Padding(
                padding: EdgeInsets.symmetric(horizontal: resolvedPadding),
                child: child,
              )
            : child;
        return Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: padded,
          ),
        );
      },
    );
  }

  Widget _buildTabSurface(BuildContext context, double inlineTabOpacity) {
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final shadow = isDark
        ? AppColors.black.withValues(alpha: 0.12)
        : AppColors.black.withValues(alpha: 0.03);
    final bottomPadding =
        widget.tabSurfaceBottomPadding ??
        (MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg);
    return Container(
      key: ValueKey<String>('${widget.keyPrefix}-tab-surface'),
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(widget.tabSurfaceTopRadius),
          topRight: Radius.circular(widget.tabSurfaceTopRadius),
          bottomLeft: Radius.circular(widget.cardRadius),
          bottomRight: Radius.circular(widget.cardRadius),
        ),
        border: Border.all(
          color: border.withValues(alpha: isDark ? 0.22 : 0.08),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: shadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(height: widget._surfaceBridge),
          if (widget.tabBarBuilder != null)
            widget.tabBarBuilder!(context, false, inlineTabOpacity),
          Padding(
            padding: EdgeInsets.only(bottom: bottomPadding),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: max(
                  0.0,
                  MediaQuery.sizeOf(context).height -
                      _toolbarHeight(context) -
                      MediaQuery.viewPaddingOf(context).bottom,
                ),
              ),
              child: widget.tabBodyBuilder(context),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    _scheduleSummaryMeasure();
    final identityProgress = _identityPinnedProgress(context);
    final primaryTabProgress = _primaryTabPinnedProgress(context);
    final toolbarOpacity = max(identityProgress, primaryTabProgress * 0.82);
    final inlineTabOpacity = (1 - (primaryTabProgress * 6)).clamp(0.0, 1.0);

    Widget scroll = NotificationListener<ScrollNotification>(
      onNotification: _handleScrollNotification,
      child: CustomScrollView(
        key: widget.scrollViewKey,
        controller: _scrollController,
        scrollCacheExtent: ScrollCacheExtent.pixels(
          MediaQuery.sizeOf(context).height * widget.cacheExtentScreens,
        ),
        physics: const BouncingScrollPhysics(
          parent: AlwaysScrollableScrollPhysics(),
        ),
        slivers: [
          SliverToBoxAdapter(
            child: SizedBox(height: _backgroundSpacerHeight(context)),
          ),
          SliverToBoxAdapter(
            child: _constrain(
              KeyedSubtree(
                key: _summaryKey,
                child: widget.summaryBuilder(context),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: _constrain(
              Transform.translate(
                offset: Offset(0, -widget._surfaceBridge),
                child: _buildTabSurface(context, inlineTabOpacity),
              ),
              horizontalPadding: widget.tabSurfaceHorizontalPadding,
            ),
          ),
        ],
      ),
    );
    if (widget.onSwipe != null) {
      scroll = GestureDetector(
        onHorizontalDragEnd: widget.onSwipe,
        child: scroll,
      );
    }

    final stackChildren = <Widget>[
      Positioned(
        top: _backgroundTop(),
        left: 0,
        right: 0,
        child: SizedBox(
          key: ValueKey<String>('${widget.keyPrefix}-background-layer'),
          height: _currentBackgroundHeight(context),
          child: widget.backgroundBuilder(context, _pullOffset),
        ),
      ),
      Positioned.fill(child: scroll),
      widget.toolbarBuilder(context, identityProgress, toolbarOpacity),
    ];

    if (widget.summaryTrackerKey != null) {
      stackChildren.add(
        Positioned(
          top:
              _backgroundSpacerHeight(context) - _scrollOffset + _rawPullOffset,
          left: 0,
          right: 0,
          child: IgnorePointer(
            child: _constrain(
              SizedBox(
                key: widget.summaryTrackerKey,
                height: AppSpacing.hairline,
              ),
            ),
          ),
        ),
      );
    }

    if (widget.tabBarBuilder != null && widget.enablePinnedTabOverlay) {
      stackChildren.add(
        Positioned(
          top: _toolbarHeight(context),
          left: 0,
          right: 0,
          child: Offstage(
            offstage: primaryTabProgress <= 0.01,
            child: IgnorePointer(
              ignoring: primaryTabProgress <= 0,
              child: Opacity(
                opacity: primaryTabProgress,
                child: _constrain(widget.tabBarBuilder!(context, true, 1.0)),
              ),
            ),
          ),
        ),
      );
    }

    Widget content = Stack(children: stackChildren);
    if (widget.bottomBar != null) {
      content = Column(
        children: [
          Expanded(child: content),
          widget.bottomBar!,
        ],
      );
    }
    return content;
  }
}
