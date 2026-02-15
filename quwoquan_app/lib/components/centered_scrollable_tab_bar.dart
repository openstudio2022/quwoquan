import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';

/// 可居中滚动的 Tab 栏
///
/// 支持：可见数自适应、左右渐隐、点击居中转场、
/// 可选锚定 Tab（锚定 Tab 在向右切换过中间后固定左侧）。
/// 适用于多 Tab 横向滚动场景（发现、圈子一级 Tab）。
///
/// 对齐策略：容器左右 padding 与内容区相同（feedContentHorizontal），
/// 芯片内部无额外 padding，文本左对齐，保证首字符与内容区左边缘对齐。
class CenteredScrollableTabBar extends ConsumerStatefulWidget {
  final List<TabItem> tabs;
  final String activeTab;
  final ValueChanged<String> onTabChange;
  final bool? isDark;
  final List<Widget> trailingActions;
  final GestureDragEndCallback? onHorizontalDragEnd;

  /// 可选：锚定 Tab ID（如圈子"推荐"），向右跨过中间 tab 后该 Tab 固定左侧
  final String? anchorTabId;

  /// 可选：可见 Tab 数量，null 时根据屏幕宽度取 3/5/7/9/11（小屏优先 5）
  final int? visibleTabCount;

  /// 仅视频深色全沉浸模式为 true 时顶栏背景透明
  final bool transparentBackground;

  /// 发现页等使用：简单左对齐滚动模式，不使用固定芯片宽度和锚定逻辑
  final bool leftAlignedCompactMode;

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
    this.leftAlignedCompactMode = false,
  });

  @override
  ConsumerState<CenteredScrollableTabBar> createState() =>
      _CenteredScrollableTabBarState();
}

class _CenteredScrollableTabBarState
    extends ConsumerState<CenteredScrollableTabBar> {
  // ===================== 滚动控制器 =====================
  /// 正常模式（未锚定固定）时使用的控制器
  final ScrollController _normalController = ScrollController();

  /// 锚定固定模式时，锚定 tab 右侧的独立 ScrollView 控制器
  ScrollController? _pinnedController;

  // ===================== 锚定状态 =====================
  bool _isAnchorPinned = false;
  bool _isAnimating = false;

  /// 缓存 LayoutBuilder 提供的实际 Tab 区域宽度（扣除 padding 和 trailing actions 后的值）。
  /// 用于精确计算 _visibleTabCount 和 _pinToggleIndex，避免用屏幕全宽导致阈值偏高。
  /// 初始值 0 表示尚未布局，此时回退到屏幕宽度估算。
  double _cachedTabAreaWidth = 0;

  static const Duration _animateDuration = Duration(milliseconds: 280);

  /// 芯片宽度
  double get _chipWidth => widget.transparentBackground
      ? AppSpacing.tabChipBaseWidthVideoImmersion
      : AppSpacing.tabChipBaseWidth;

  /// 芯片步进宽度（芯片 + 间距），用于计算滚动偏移
  double get _chipStep => _chipWidth + AppSpacing.primaryTabChipGap;

  double get _gradientWidth =>
      16.0 + (_visibleTabCount - 3).clamp(0, 8) * 2;

  /// 可见 Tab 数量（允许偶数），用于锚定阈值与渐隐宽度。
  /// 优先使用 LayoutBuilder 缓存的实际 Tab 区域宽度（精确），
  /// 首帧尚无缓存时回退到屏幕宽度（略大，但仅影响初始状态）。
  int get _visibleTabCount {
    if (widget.visibleTabCount != null) {
      return widget.visibleTabCount!.clamp(3, 13);
    }
    final width = _cachedTabAreaWidth > 0
        ? _cachedTabAreaWidth
        : MediaQuery.sizeOf(context).width;
    return (width / _chipStep).floor().clamp(3, 13);
  }

  int get _anchorIndex {
    if (widget.anchorTabId == null) return -1;
    return widget.tabs.indexWhere((t) => t.id == widget.anchorTabId);
  }

  /// 锚定切换阈值：居中滚动不会导致首位 tab（关注）被推出屏幕的最大 activeIndex。
  ///
  /// 推导：居中 index N 时 scrollOffset = N * chipStep - (viewportWidth - chipWidth) / 2。
  /// offset > 0 时首位 tab 开始移出 → 阈值 = floor((viewportWidth - chipWidth) / (2 * chipStep))。
  /// activeIndex > 阈值时触发锚定，首位 tab 从完全可见直接变为完全隐藏，不会部分裁切。
  int get _pinToggleIndex {
    final width = _cachedTabAreaWidth > 0
        ? _cachedTabAreaWidth
        : MediaQuery.sizeOf(context).width;
    final threshold = ((width - _chipWidth) / (2 * _chipStep)).floor();
    return threshold.clamp(1, widget.tabs.length - 1);
  }

  // ===================== 生命周期 =====================

  /// initState 阶段不能访问 MediaQuery（InheritedWidget），
  /// 锚定初始同步延迟到 didChangeDependencies。
  bool _needsInitialSync = true;

  @override
  void initState() {
    super.initState();
    _normalController.addListener(_onScroll);
    // 注意：_syncAnchorMode 依赖 _visibleTabCount → MediaQuery，
    // 不能在 initState 调用，移至 didChangeDependencies
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _scrollToActiveTab(animate: false);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_needsInitialSync) {
      _needsInitialSync = false;
      _syncAnchorMode(force: true);
      if (_isAnchorPinned) {
        _pinnedController = ScrollController();
        _pinnedController!.addListener(_onScroll);
      }
    }
  }

  @override
  void dispose() {
    _normalController.removeListener(_onScroll);
    _normalController.dispose();
    _pinnedController?.removeListener(_onScroll);
    _pinnedController?.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(CenteredScrollableTabBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    final wasPinned = _isAnchorPinned;
    if (oldWidget.activeTab != widget.activeTab ||
        oldWidget.tabs != widget.tabs) {
      _syncAnchorMode(force: false);
    }
    final pinChanged = wasPinned != _isAnchorPinned;
    if (pinChanged) {
      _onPinStateChanged();
    }
    if (!pinChanged &&
        oldWidget.activeTab != widget.activeTab &&
        !_isAnimating) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _scrollToActiveTab(animate: true);
      });
    }
  }

  // ===================== 锚定状态机 =====================

  /// 根据当前激活 tab 更新锚定状态。
  ///
  /// 规则（基于视觉中间位）：
  /// - 初始不锚定（关注可见在首位）
  /// - 向右切换：activeIndex > centerSlot 时进入锚定
  ///   （居中会导致首位 tab 滚出屏幕）
  /// - 向左切换：activeIndex <= centerSlot 时退出锚定
  ///   （关注能回到可见区域）
  void _syncAnchorMode({required bool force}) {
    final i = _anchorIndex;
    if (i < 0) {
      _isAnchorPinned = false;
      return;
    }
    final activeIndex =
        widget.tabs.indexWhere((t) => t.id == widget.activeTab);
    if (activeIndex < 0) return;
    final centerSlot = _pinToggleIndex;
    if (force) {
      _isAnchorPinned = activeIndex > centerSlot;
      return;
    }
    if (_isAnchorPinned && activeIndex <= centerSlot) {
      _isAnchorPinned = false;
    } else if (!_isAnchorPinned && activeIndex > centerSlot) {
      _isAnchorPinned = true;
    }
  }

  /// 锚定状态切换后，创建/销毁对应的 ScrollController。
  void _onPinStateChanged() {
    if (_isAnchorPinned) {
      // 进入固定模式：创建固定区域专用控制器
      _pinnedController?.removeListener(_onScroll);
      _pinnedController?.dispose();
      _pinnedController = ScrollController();
      _pinnedController!.addListener(_onScroll);
    } else {
      // 退出固定模式：销毁固定区域控制器，回到正常模式
      _pinnedController?.removeListener(_onScroll);
      _pinnedController?.dispose();
      _pinnedController = null;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _scrollToActiveTab(animate: false);
    });
  }

  // ===================== 滚动 =====================

  void _onScroll() {
    if (mounted) setState(() {});
  }

  ScrollController get _activeController =>
      _isAnchorPinned
          ? (_pinnedController ?? _normalController)
          : _normalController;

  Future<void> _scrollToActiveTab({bool animate = true}) async {
    if (widget.leftAlignedCompactMode) return;
    final controller = _activeController;
    if (!controller.hasClients) return;
    final activeIndex =
        widget.tabs.indexWhere((t) => t.id == widget.activeTab);
    if (activeIndex < 0) return;

    final int effectiveIndex;
    if (_isAnchorPinned) {
      effectiveIndex = activeIndex - (_anchorIndex + 1);
      if (effectiveIndex < 0) return;
    } else {
      effectiveIndex = activeIndex;
    }

    final viewportWidth = controller.position.viewportDimension;
    if (viewportWidth <= 0) return;
    final maxExt = controller.position.maxScrollExtent;
    final currentOffset = controller.offset;

    // 居中策略：将 active tab 的中心对齐到「整个 Tab 栏容器」中心。
    // clamp 到 [0, maxExt] 自然处理两侧边界不足的情况：
    //   - 左边不足（如推荐前只有关注）→ clamp 到 0，tab 靠左显示
    //   - 右边不足（如美食后无 tab）→ clamp 到 maxExt，tab 靠右显示
    final tabLeft = effectiveIndex * _chipStep;

    final double target;
    if (_isAnchorPinned) {
      // 固定模式：锚定 tab 的 chipStep slot 占据左侧，滚动区 viewport 较窄。
      //   containerWidth = viewportWidth + chipStep（固定 slot）
      //   tabCenterInContainer = chipStep + tabLeft + chipWidth/2 - scrollOffset
      //   设 tabCenterInContainer = containerWidth / 2，解出 scrollOffset:
      final idealTarget =
          tabLeft + _chipStep / 2 + _chipWidth / 2 - viewportWidth / 2;
      // Snap 到 chipStep 整数倍：确保锚定 tab 右侧的首个滚动 tab
      // 要么完全可见、要么完全隐藏，不出现部分裁切。
      // 间距一致性优先于严格居中（偏差 ≤ chipStep/2，视觉可接受）。
      if (_chipStep > 0) {
        final snapped = (idealTarget / _chipStep).round() * _chipStep;
        if (snapped > maxExt) {
          // 尾部边界：snap 值超出 maxExt，floor 到 maxExt 内最大 chipStep 倍数，
          // 保持间距一致，剩余 tab 全部可见不再滚动。
          target = (maxExt / _chipStep).floor() * _chipStep;
        } else {
          target = snapped.clamp(0.0, maxExt);
        }
      } else {
        target = idealTarget.clamp(0.0, maxExt);
      }
    } else {
      // 正常模式：整个 Tab 栏即滚动区，直接居中
      final idealTarget = tabLeft - (viewportWidth - _chipWidth) / 2;
      target = idealTarget.clamp(0.0, maxExt);
    }
    if ((target - currentOffset).abs() < 1) return; // 无需滚动

    if (animate) {
      _isAnimating = true;
      await controller.animateTo(
        target,
        duration: _animateDuration,
        curve: Curves.easeOut,
      );
      if (mounted) _isAnimating = false;
    } else {
      controller.jumpTo(target);
    }
  }

  void _onTabTapped(String tabId) {
    widget.onTabChange(tabId);
    // didUpdateWidget → _scrollToActiveTab 会处理滚动
  }

  // ===================== 构建 =====================

  @override
  Widget build(BuildContext context) {
    _syncAnchorMode(force: false);

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
    final horizontalPadding = AppSpacing.feedContentHorizontal(context);

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
              child: _buildTabLayout(currentIsDark, fg, fgUnselected, bg),
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

  Widget _buildTabLayout(
      bool isDark, Color fg, Color fgUnselected, Color bg) {
    if (widget.leftAlignedCompactMode) {
      return _buildLeftAlignedLayout(isDark, fg, fgUnselected);
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        // 缓存实际 Tab 区域宽度，用于 _visibleTabCount / _pinToggleIndex 精确计算
        _cachedTabAreaWidth = constraints.maxWidth;
        if (_isAnchorPinned && _anchorIndex >= 0) {
          return _buildPinnedLayout(isDark, fg, fgUnselected, bg);
        }
        return _buildNormalLayout(isDark, fg, fgUnselected, bg);
      },
    );
  }

  // --------------- 正常模式 ---------------

  Widget _buildNormalLayout(
      bool isDark, Color fg, Color fgUnselected, Color bg) {
    final offset =
        _normalController.hasClients ? _normalController.offset : 0.0;
    final maxExt = _normalController.hasClients
        ? _normalController.position.maxScrollExtent
        : 0.0;
    final showLeftGradient =
        offset > 4 && !widget.transparentBackground;
    final showRightGradient =
        offset < maxExt - 4 && !widget.transparentBackground;

    return Stack(
      clipBehavior: Clip.none,
      children: [
        SingleChildScrollView(
          controller: _normalController,
          scrollDirection: Axis.horizontal,
          physics: const ClampingScrollPhysics(),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (int i = 0; i < widget.tabs.length; i++)
                _buildChipSlot(widget.tabs[i], isDark, fg, fgUnselected),
            ],
          ),
        ),
        if (showLeftGradient)
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            child: _buildGradient(bg, isLeft: true),
          ),
        if (showRightGradient)
          Positioned(
            right: 0,
            top: 0,
            bottom: 0,
            child: _buildGradient(bg, isLeft: false),
          ),
      ],
    );
  }

  // --------------- 锚定固定模式（Row 拆分，无 Stack/Clip 叠加） ---------------

  Widget _buildPinnedLayout(
      bool isDark, Color fg, Color fgUnselected, Color bg) {
    final anchorTab = widget.tabs[_anchorIndex];
    final restTabs = widget.tabs.sublist(_anchorIndex + 1);
    final controller = _pinnedController ?? _normalController;

    return Row(
      children: [
        // 固定锚定 Tab —— 始终可见在最左侧
        // chipStep slot 自带尾部间距，无需额外 SizedBox(gap)
        _buildChipSlot(anchorTab, isDark, fg, fgUnselected),
        // 右侧剩余 Tab 独立可滚动
        Expanded(
          child: SingleChildScrollView(
            controller: controller,
            scrollDirection: Axis.horizontal,
            physics: const ClampingScrollPhysics(),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (int i = 0; i < restTabs.length; i++)
                  _buildChipSlot(restTabs[i], isDark, fg, fgUnselected),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // --------------- 发现页左对齐紧凑模式 ---------------

  Widget _buildLeftAlignedLayout(
      bool isDark, Color fg, Color fgUnselected) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const ClampingScrollPhysics(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (int i = 0; i < widget.tabs.length; i++)
            _buildChipSlot(widget.tabs[i], isDark, fg, fgUnselected),
        ],
      ),
    );
  }

  // --------------- 芯片构建 ---------------

  /// 统一的芯片插槽：SizedBox(chipStep) 包裹。
  /// 每个 slot = chipWidth(芯片) + 尾部空白(gap)，slot 自带间距，
  /// 无需在 Row 中额外添加 SizedBox(gap)，避免 pinned 模式双间距 bug。
  Widget _buildChipSlot(
      TabItem tab, bool isDark, Color fg, Color fgUnselected) {
    return SizedBox(
      width: _chipStep,
      child: _buildTabChip(
        context: context,
        tab: tab,
        selected: tab.id == widget.activeTab,
        isDark: isDark,
        fg: fg,
        fgUnselected: fgUnselected,
        onTap: () => _onTabTapped(tab.id),
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
        child: ConstrainedBox(
          constraints: BoxConstraints(
            minWidth: AppSpacing.minInteractiveSize,
            minHeight: AppSpacing.minInteractiveSize,
          ),
          // 无额外内部 padding；文字左对齐以保证首字符与内容区左边缘对齐
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                tab.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: textStyle,
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
    );
  }

  Widget _buildGradient(Color bg, {required bool isLeft}) {
    return IgnorePointer(
      child: Container(
        width: _gradientWidth,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: isLeft ? Alignment.centerLeft : Alignment.centerRight,
            end: isLeft ? Alignment.centerRight : Alignment.centerLeft,
            colors: [bg, bg.withValues(alpha: 0)],
          ),
        ),
      ),
    );
  }
}
