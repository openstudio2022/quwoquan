import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 评论排序锚定菜单的弹出方向。
///
/// 业务语义：默认向下展开；当下方空间不足以完整显示菜单（会被底部工具栏遮挡）时翻转向上。
enum CommentSortMenuPlacement { below, above }

/// 纯函数：根据触发器位置与可用视口计算菜单应向上还是向下弹出。
///
/// - [viewportTop] / [viewportBottom] 是允许放置菜单的安全区上下边界，
///   调用方需把底部工具栏高度从 [viewportBottom] 中预留出去，确保菜单不遮挡工具栏。
/// - 默认向下；下方放不下时尝试向上；两侧都放不下时选择更大的一侧。
CommentSortMenuPlacement resolveCommentSortMenuPlacement({
  required double triggerTop,
  required double triggerBottom,
  required double menuHeight,
  required double viewportTop,
  required double viewportBottom,
  double gap = AppSpacing.xs,
}) {
  final spaceBelow = viewportBottom - (triggerBottom + gap);
  if (spaceBelow >= menuHeight) {
    return CommentSortMenuPlacement.below;
  }
  final spaceAbove = (triggerTop - gap) - viewportTop;
  if (spaceAbove >= menuHeight) {
    return CommentSortMenuPlacement.above;
  }
  return spaceBelow >= spaceAbove
      ? CommentSortMenuPlacement.below
      : CommentSortMenuPlacement.above;
}

String commentSortModeLabel(CommentSortMode mode) {
  switch (mode) {
    case CommentSortMode.recommended:
      return UITextConstants.commentSortRecommended;
    case CommentSortMode.latest:
      return UITextConstants.circleSortLatest;
    case CommentSortMode.mostLiked:
      return UITextConstants.commentSortMostLiked;
  }
}

ValueKey<String> _menuItemKey(CommentSortMode mode) {
  switch (mode) {
    case CommentSortMode.recommended:
      return TestKeys.commentSortMenuItemRecommended;
    case CommentSortMode.latest:
      return TestKeys.commentSortMenuItemLatest;
    case CommentSortMode.mostLiked:
      return TestKeys.commentSortMenuItemMostLiked;
  }
}

/// 评论排序锚定菜单按钮。
///
/// 与「我的主页记录区」筛选框一致：单一胶囊按钮显示当前排序（默认综合），
/// 点击弹出菜单，菜单自适应上/下翻转避让底部工具栏。
class CommentSortMenuButton extends StatefulWidget {
  const CommentSortMenuButton({
    super.key,
    required this.isDark,
    required this.sortMode,
    required this.onChanged,
    this.bottomReserve = 0,
  });

  final bool isDark;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onChanged;

  /// 底部需要预留、不可被菜单遮挡的高度（例如底部评论工具栏）。
  final double bottomReserve;

  @override
  State<CommentSortMenuButton> createState() => _CommentSortMenuButtonState();
}

class _CommentSortMenuButtonState extends State<CommentSortMenuButton> {
  final GlobalKey _triggerKey = GlobalKey();
  OverlayEntry? _entry;

  static const List<CommentSortMode> _orderedModes = [
    CommentSortMode.recommended,
    CommentSortMode.latest,
    CommentSortMode.mostLiked,
  ];

  @override
  void dispose() {
    _removeMenu();
    super.dispose();
  }

  void _removeMenu() {
    _entry?.remove();
    _entry = null;
  }

  void _toggleMenu() {
    if (_entry != null) {
      _removeMenu();
      return;
    }
    final renderBox =
        _triggerKey.currentContext?.findRenderObject() as RenderBox?;
    final overlay = Overlay.of(context);
    if (renderBox == null || !renderBox.hasSize) {
      return;
    }
    final overlayBox = overlay.context.findRenderObject() as RenderBox?;
    if (overlayBox == null) {
      return;
    }

    final triggerTopLeft = renderBox.localToGlobal(
      Offset.zero,
      ancestor: overlayBox,
    );
    final triggerSize = renderBox.size;
    final triggerRect = triggerTopLeft & triggerSize;

    final media = MediaQuery.of(context);
    final overlaySize = overlayBox.size;
    final menuWidth = AppSpacing.commentSortMenuMinWidth;
    final menuHeight =
        AppSpacing.commentSortMenuItemHeight * _orderedModes.length;

    final viewportTop = media.padding.top + AppSpacing.xs;
    final viewportBottom =
        overlaySize.height - media.padding.bottom - widget.bottomReserve;

    final placement = resolveCommentSortMenuPlacement(
      triggerTop: triggerRect.top,
      triggerBottom: triggerRect.bottom,
      menuHeight: menuHeight,
      viewportTop: viewportTop,
      viewportBottom: viewportBottom,
    );

    final double menuTop;
    if (placement == CommentSortMenuPlacement.below) {
      menuTop = triggerRect.bottom + AppSpacing.xs;
    } else {
      menuTop = triggerRect.top - AppSpacing.xs - menuHeight;
    }

    final double maxLeft = overlaySize.width - menuWidth - AppSpacing.md;
    final double safeMaxLeft = maxLeft < AppSpacing.md
        ? AppSpacing.md
        : maxLeft;
    final double rawLeft = triggerRect.right - menuWidth;
    final double menuLeft = rawLeft < AppSpacing.md
        ? AppSpacing.md
        : (rawLeft > safeMaxLeft ? safeMaxLeft : rawLeft);

    _entry = OverlayEntry(
      builder: (context) {
        return _SortMenuOverlay(
          isDark: widget.isDark,
          left: menuLeft,
          top: menuTop,
          width: menuWidth,
          modes: _orderedModes,
          activeMode: widget.sortMode,
          onSelected: (mode) {
            _removeMenu();
            if (mode != widget.sortMode) {
              widget.onChanged(mode);
            }
          },
          onDismiss: _removeMenu,
        );
      },
    );
    overlay.insert(_entry!);
  }

  @override
  Widget build(BuildContext context) {
    final label = commentSortModeLabel(widget.sortMode);
    return GestureDetector(
      key: _triggerKey,
      behavior: HitTestBehavior.opaque,
      onTap: _toggleMenu,
      child: Semantics(
        button: true,
        label: '${UITextConstants.commentSortMenuSemanticLabel} $label',
        child: Container(
          key: TestKeys.commentSortMenuButton,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(
              widget.isDark,
              ColorType.surfaceMuted,
            ),
            borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.medium,
                  color: AppColorsFunctional.getColor(
                    widget.isDark,
                    ColorType.foregroundPrimary,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.xs),
              Icon(
                CupertinoIcons.chevron_down,
                size: AppSpacing.iconSmall,
                color: AppColorsFunctional.getColor(
                  widget.isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SortMenuOverlay extends StatelessWidget {
  const _SortMenuOverlay({
    required this.isDark,
    required this.left,
    required this.top,
    required this.width,
    required this.modes,
    required this.activeMode,
    required this.onSelected,
    required this.onDismiss,
  });

  final bool isDark;
  final double left;
  final double top;
  final double width;
  final List<CommentSortMode> modes;
  final CommentSortMode activeMode;
  final ValueChanged<CommentSortMode> onSelected;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final textColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return CupertinoTheme(
      data: CupertinoTheme.of(context),
      child: DefaultTextStyle(
        style: TextStyle(
          color: textColor,
          fontSize: AppTypography.sm,
          decoration: TextDecoration.none,
        ),
        child: Material(
          type: MaterialType.transparency,
          child: Stack(
            key: TestKeys.commentSortMenuOverlay,
            children: [
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onDismiss,
                ),
              ),
              Positioned(
                left: left,
                top: top,
                width: width,
                // iOS 锚定菜单：大圆角、无硬边框、柔和阴影；
                // 按压底色由 ClipRRect 裁出圆角，避免方角溢出。
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.surfaceElevated,
                    ),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.black.withValues(
                          alpha: isDark ? 0.5 : 0.16,
                        ),
                        blurRadius: AppSpacing.lg,
                        offset: Offset(0, AppSpacing.xs),
                      ),
                    ],
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        for (final mode in modes)
                          _SortMenuItem(
                            isDark: isDark,
                            mode: mode,
                            isActive: mode == activeMode,
                            onTap: () => onSelected(mode),
                          ),
                      ],
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

class _SortMenuItem extends StatefulWidget {
  const _SortMenuItem({
    required this.isDark,
    required this.mode,
    required this.isActive,
    required this.onTap,
  });

  final bool isDark;
  final CommentSortMode mode;
  final bool isActive;
  final VoidCallback onTap;

  @override
  State<_SortMenuItem> createState() => _SortMenuItemState();
}

class _SortMenuItemState extends State<_SortMenuItem> {
  bool _pressed = false;

  void _setPressed(bool value) {
    if (_pressed == value) return;
    setState(() => _pressed = value);
  }

  @override
  Widget build(BuildContext context) {
    final activeColor = AppColors.primaryColor;
    final labelColor = widget.isActive
        ? activeColor
        : AppColorsFunctional.getColor(
            widget.isDark,
            ColorType.foregroundPrimary,
          );
    final Color background;
    if (_pressed) {
      background = AppColorsFunctional.getColor(
        widget.isDark,
        ColorType.surfaceMuted,
      );
    } else if (widget.isActive) {
      background = activeColor.withValues(alpha: 0.08);
    } else {
      background = AppColors.transparent;
    }
    return GestureDetector(
      key: _menuItemKey(widget.mode),
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => _setPressed(true),
      onTapCancel: () => _setPressed(false),
      onTapUp: (_) => _setPressed(false),
      onTap: widget.onTap,
      child: Container(
        height: AppSpacing.commentSortMenuItemHeight,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        alignment: Alignment.centerLeft,
        color: background,
        child: Row(
          children: [
            Expanded(
              child: Text(
                commentSortModeLabel(widget.mode),
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: widget.isActive
                      ? AppTypography.semiBold
                      : AppTypography.regular,
                  color: labelColor,
                ),
              ),
            ),
            if (widget.isActive)
              Icon(
                CupertinoIcons.check_mark,
                size: AppSpacing.iconSmall,
                color: activeColor,
              ),
          ],
        ),
      ),
    );
  }
}
