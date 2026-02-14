import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';

/// 可居中滚动的 Tab 栏
///
/// 支持：可见数 3/5/7/9/11 自适应（小屏优先 5）、左右渐隐、点击居中转场、
/// 可选锚定 Tab（锚定 Tab 选中时贴左）、滑动结束居中吸附。居中对齐，非左对齐。
/// 适用于多 Tab 横向滚动场景（发现、圈子一级 Tab）。
class CenteredScrollableTabBar extends ConsumerStatefulWidget {
  final List<TabItem> tabs;
  final String activeTab;
  final ValueChanged<String> onTabChange;
  final bool? isDark;
  final List<Widget> trailingActions;
  final GestureDragEndCallback? onHorizontalDragEnd;

  /// 可选：锚定 Tab ID（如圈子"推荐"），选中时该 Tab 固定左侧而非居中
  final String? anchorTabId;

  /// 可选：可见 Tab 数量，null 时根据屏幕宽度取 3/5/7/9/11（小屏优先 5）
  final int? visibleTabCount;

  /// 仅视频深色全沉浸模式为 true 时顶栏背景透明，便于视频全屏透出；普通深色模式仍不透明
  final bool transparentBackground;

  const CenteredScrollableTabBar({
    super.key,
    required this.tabs,
    required this.activeTab,
    required this.onTabChange,
    this.isDark,
    this.trailingActions = const [],
    this.onHorizontalDragEnd,
    this.anchorTabId,
    this.visibleTabCount,
    this.transparentBackground = false,
  });

  @override
  ConsumerState<CenteredScrollableTabBar> createState() =>
      _CenteredScrollableTabBarState();
}

class _CenteredScrollableTabBarState extends ConsumerState<CenteredScrollableTabBar> {
  late ScrollController _scrollController;
  bool _isAnchorPinned = false;
  double _tabAreaWidth = 0;

  /// 芯片宽度；视频沉浸时略大，避免「视频」两字被裁切导致只有「视」亮色
  double get _chipWidth => widget.transparentBackground
      ? AppSpacing.tabChipBaseWidthVideoImmersion
      : AppSpacing.tabChipBaseWidth;

  double get _gradientWidth =>
      16.0 + (_visibleTabCount - 3).clamp(0, 8) * 2;
  static const Duration _animateDuration = Duration(milliseconds: 280);

  /// 当前 scroll offset，用于左右渐变显隐
  double _scrollOffset = 0;

  int _normalizeVisibleTabCount(int raw) {
    var value = raw;
    if (value < 3) value = 3;
    if (value > 13) value = 13;
    if (value.isEven) value = value - 1;
    return value;
  }

  /// 可见 Tab 数量：支持 3/5/7/9/11/13；手机默认 5
  int get _visibleTabCount {
    if (widget.visibleTabCount != null) {
      return _normalizeVisibleTabCount(widget.visibleTabCount!);
    }
    final width = MediaQuery.sizeOf(context).width;
    if (width < 320) return 3;
    if (width < 600) return 5;
    if (width < 900) return 7;
    return 9;
  }

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scrollController.hasClients) {
        _scrollToCenterActive();
      }
    });
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  bool _isAnimating = false;

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final offset = _scrollController.offset;
    if (offset != _scrollOffset) {
      _scrollOffset = offset;
      _syncAnchorModeWithOffset(offset);
      if (mounted) setState(() {});
    }
  }

  int get _anchorIndex {
    if (widget.anchorTabId == null) return -1;
    return widget.tabs.indexWhere((t) => t.id == widget.anchorTabId);
  }

  double get _pinThresholdOffset {
    final i = _anchorIndex;
    if (i < 0) return 0;
    return i * _chipWidth;
  }

  void _syncAnchorModeWithOffset(double currentOffset) {
    final i = _anchorIndex;
    if (i < 0) {
      if (_isAnchorPinned) _isAnchorPinned = false;
      return;
    }
    final nextPinned = currentOffset >= _pinThresholdOffset;
    if (nextPinned != _isAnchorPinned) {
      _isAnchorPinned = nextPinned;
    }
  }

  @override
  void didUpdateWidget(CenteredScrollableTabBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.activeTab != widget.activeTab && !_isAnimating) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _scrollToCenterActive();
      });
    }
  }

  double _computeFullOffsetToCenterIndex(int index) {
    final viewportWidth = _tabAreaWidth;
    if (viewportWidth <= 0) return 0;
    final tabCenter = index * _chipWidth + _chipWidth / 2;
    final viewportCenter = viewportWidth / 2;
    final target = tabCenter - viewportCenter;
    final fullMax = (widget.tabs.length * _chipWidth - viewportWidth).clamp(0.0, double.infinity);
    return target.clamp(0.0, fullMax);
  }

  Future<void> _animateToLogicalOffset({
    required double fullOffset,
    required bool pinAfter,
  }) async {
    if (!_scrollController.hasClients) return;
    final maxExt = _scrollController.position.maxScrollExtent;
    final target = fullOffset.clamp(0.0, maxExt);
    _isAnimating = true;
    await _scrollController.animateTo(
      target,
      duration: _animateDuration,
      curve: Curves.easeOut,
    );
    if (mounted) _isAnimating = false;
  }

  Future<void> _scrollToCenterActive() async {
    final index = widget.tabs.indexWhere((t) => t.id == widget.activeTab);
    if (index < 0) return;
    final isAnchorSelected =
        widget.anchorTabId != null && widget.activeTab == widget.anchorTabId;
    final fullOffset =
        isAnchorSelected ? 0.0 : _computeFullOffsetToCenterIndex(index);
    final pinAfter = !isAnchorSelected &&
        _anchorIndex >= 0 &&
        fullOffset >= _pinThresholdOffset;
    await _animateToLogicalOffset(fullOffset: fullOffset, pinAfter: pinAfter);
  }

  void _onTabTapped(String tabId) {
    final index = widget.tabs.indexWhere((t) => t.id == tabId);
    if (index < 0) return;
    final isAnchorTapped = widget.anchorTabId != null && tabId == widget.anchorTabId;
    final fullOffset =
        isAnchorTapped ? 0.0 : _computeFullOffsetToCenterIndex(index);
    final pinAfter = !isAnchorTapped &&
        _anchorIndex >= 0 &&
        fullOffset >= _pinThresholdOffset;
    // 先切换选中，再做滚动动画，避免点击时出现“等动画结束才切页”的跳跃感。
    widget.onTabChange(tabId);
    _animateToLogicalOffset(fullOffset: fullOffset, pinAfter: pinAfter);
  }

  @override
  Widget build(BuildContext context) {
    final currentIsDark =
        (widget.isDark ?? ref.watch(effectiveIsDarkProvider))!;
    final isVideoImmersion = widget.transparentBackground;
    final bg = isVideoImmersion
        ? Colors.transparent
        : AppColorsFunctional.getColor(
            currentIsDark,
            ColorType.backgroundPrimary,
          );
    final fg = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.foregroundSecondary,
    );
    final fgUnselected = isVideoImmersion && currentIsDark
        ? AppColorsFunctional.getColor(
            currentIsDark,
            ColorType.foregroundTertiary,
          )
        : fgSecondary;
    final borderColor = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.borderPrimary,
    );
    final horizontalPadding = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.feedContentHorizontal(context),
      regular: AppSpacing.feedContentHorizontal(context),
      expanded: AppSpacing.feedContentHorizontal(context),
    );

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        color: bg,
        border: isVideoImmersion
            ? null
            : Border(
                bottom: BorderSide(
                  color: borderColor.withValues(alpha: 0.3),
                  width: 0.5,
                ),
              ),
      ),
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: widget.onHorizontalDragEnd,
              child: LayoutBuilder(
                builder: (context, constraints) {
                  _tabAreaWidth = constraints.maxWidth;
                  final hasAnchor = widget.anchorTabId != null;
                  final anchorIndex = _anchorIndex;
                  final canPin = hasAnchor && anchorIndex >= 0;
                  final threshold = _pinThresholdOffset;
                  final isPinned = canPin && _scrollOffset >= threshold;
                  final isPrePinLeading = canPin &&
                      !isPinned &&
                      anchorIndex > 0 &&
                      _scrollOffset > 0 &&
                      _scrollOffset < threshold;
                  final fixedLeftTab = isPinned
                      ? widget.tabs[anchorIndex]
                      : (isPrePinLeading ? widget.tabs[anchorIndex - 1] : null);
                  final tailTabs = widget.tabs;
                  final maxExt = _scrollController.hasClients
                      ? _scrollController.position.maxScrollExtent
                      : 0.0;
                  final showLeftGradient = _scrollOffset > 4 && !hasAnchor &&
                      !widget.transparentBackground;
                  final showRightGradient = _scrollOffset < maxExt - 4 &&
                      !widget.transparentBackground;
                  return Stack(
                    clipBehavior: Clip.none,
                    children: [
                      NotificationListener<ScrollNotification>(
                        onNotification: (n) {
                          if (n is ScrollUpdateNotification ||
                              n is ScrollEndNotification) {
                            _onScroll();
                          }
                          return false;
                        },
                        child: ClipRect(
                          clipper: _LeftInsetClipper(
                            leftInset: fixedLeftTab == null ? 0 : _chipWidth,
                          ),
                          child: SingleChildScrollView(
                            controller: _scrollController,
                            scrollDirection: Axis.horizontal,
                            physics: const ClampingScrollPhysics(),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: tailTabs.map((tab) {
                                return SizedBox(
                                  width: _chipWidth,
                                  child: _buildTabChip(
                                    context: context,
                                    tab: tab,
                                    selected: tab.id == widget.activeTab,
                                    isDark: currentIsDark,
                                    fg: fg,
                                    fgUnselected: fgUnselected,
                                    onTap: () => _onTabTapped(tab.id),
                                  ),
                                );
                              }).toList(),
                              ),
                            ),
                          ),
                      ),
                      if (fixedLeftTab != null)
                        Positioned(
                          left: 0,
                          top: 0,
                          bottom: 0,
                          child: SizedBox(
                            width: _chipWidth,
                            child: _buildTabChip(
                              context: context,
                              tab: fixedLeftTab,
                              selected: fixedLeftTab.id == widget.activeTab,
                              isDark: currentIsDark,
                              fg: fg,
                              fgUnselected: fgUnselected,
                              onTap: () => _onTabTapped(fixedLeftTab.id),
                            ),
                          ),
                        ),
                      if (showLeftGradient)
                        Positioned(
                          left: 0,
                          top: 0,
                          bottom: 0,
                          child: IgnorePointer(
                            child: Container(
                              width: _gradientWidth,
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  begin: Alignment.centerLeft,
                                  end: Alignment.centerRight,
                                  colors: [bg, bg.withValues(alpha: 0)],
                                ),
                              ),
                            ),
                          ),
                        ),
                      if (showRightGradient)
                        Positioned(
                          right: 0,
                          top: 0,
                          bottom: 0,
                          child: IgnorePointer(
                            child: Container(
                              width: _gradientWidth,
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  begin: Alignment.centerRight,
                                  end: Alignment.centerLeft,
                                  colors: [bg, bg.withValues(alpha: 0)],
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ),
          if (widget.trailingActions.isNotEmpty) ...[
            SizedBox(width: AppSpacing.intraGroupXs),
            ...widget.trailingActions,
          ],
        ],
      ),
    );
  }

  Widget _buildTabChip({
    required BuildContext context,
    required TabItem tab,
    required bool selected,
    required bool isDark,
    required Color fg,
    required Color fgUnselected,
    required VoidCallback onTap,
  }) {
    final chipFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.base,
      regular: AppTypography.lg,
      expanded: AppTypography.xl,
    );
    final textStyle = TextStyle(
      fontSize: chipFontSize,
      fontWeight: selected ? AppTypography.bold : AppTypography.medium,
      color: selected ? fg : fgUnselected,
    );
    final textPainter = TextPainter(
      text: TextSpan(text: tab.label, style: textStyle),
      maxLines: 1,
      textDirection: TextDirection.ltr,
    )..layout();
    final underlineWidth = textPainter.width;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.intraGroupSm,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minWidth: AppSpacing.minInteractiveSize,
              minHeight: AppSpacing.minInteractiveSize,
            ),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      tab.label,
                      maxLines: 1,
                      textAlign: TextAlign.center,
                      style: textStyle,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  SizedBox(
                    width: underlineWidth,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      height: AppSpacing.intraGroupXs / 2,
                      decoration: BoxDecoration(
                        color: selected ? fg : Colors.transparent,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.intraGroupXs / 4,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LeftInsetClipper extends CustomClipper<Rect> {
  const _LeftInsetClipper({required this.leftInset});

  final double leftInset;

  @override
  Rect getClip(Size size) {
    final left = leftInset.clamp(0, size.width);
    return Rect.fromLTWH(
      left.toDouble(),
      0,
      (size.width - left).clamp(0, size.width).toDouble(),
      size.height,
    );
  }

  @override
  bool shouldReclip(covariant _LeftInsetClipper oldClipper) {
    return oldClipper.leftInset != leftInset;
  }
}

