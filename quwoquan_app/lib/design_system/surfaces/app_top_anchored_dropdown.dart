import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';

/// 顶部锚定下滑浮层（dropdown）。
///
/// 与贴底的 [showModalBottomSheet] / `showAppBottomModal` 形成对照：本浮层从
/// [anchorTop]（通常是触发器/顶栏底边的全局 Y 坐标）向下展开，呈现「从触发器下方滑出」
/// 的语义，适用于相册选择、就近筛选切换等下拉场景。统一一处实现，避免各页各写一套锚定浮层。
///
/// 行为契约：
/// - 自适应高度：浮层高度由内容决定，并被 [maxHeight] 裁剪；默认封顶到 [anchorTop]
///   以下的可用内容区（屏幕高度 - anchorTop - 底部安全区 - [bottomSafeGap]），不越界；
/// - 亮度层关闭：浮层外为原地淡入的亮度层，点击即关闭（[Navigator.pop] 返回 null）；
/// - 下滑动画：浮层「自顶向下揭示 + 淡入」呈现，关闭时反向收起。
///
/// [builder] 返回浮层面板内容；其根部建议是带圆角与背景的容器，宽度由 [horizontalMargin]
/// 留白后撑满。返回值为面板内 [Navigator.pop] 带出的选择结果。
Future<T?> showAppTopAnchoredDropdown<T>({
  required BuildContext context,
  required double anchorTop,
  required WidgetBuilder builder,
  required String barrierLabel,
  Color? scrimColor,
  double horizontalMargin = 0,
  double bottomSafeGap = 0,
  double? maxHeight,
  Duration transitionDuration = const Duration(milliseconds: 220),
  bool useRootNavigator = true,
}) {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final themes = InheritedTheme.capture(from: context, to: navigator.context);
  return navigator.push<T>(
    PageRouteBuilder<T>(
      opaque: false,
      barrierDismissible: true,
      barrierLabel: barrierLabel,
      barrierColor: AppColors.transparent,
      transitionDuration: transitionDuration,
      reverseTransitionDuration: transitionDuration,
      pageBuilder: (ctx, animation, secondaryAnimation) =>
          const SizedBox.shrink(),
      transitionsBuilder: (ctx, animation, secondaryAnimation, child) {
        final media = MediaQuery.of(ctx);
        final available =
            media.size.height -
            anchorTop -
            media.viewPadding.bottom -
            bottomSafeGap;
        final resolvedMax =
            maxHeight ?? (available <= 0 ? media.size.height : available);
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return Stack(
          fit: StackFit.expand,
          children: <Widget>[
            FadeTransition(
              opacity: curved,
              child: AppModalBrightnessLayer(color: scrimColor),
            ),
            Positioned(
              top: anchorTop,
              left: horizontalMargin,
              right: horizontalMargin,
              child: Align(
                alignment: Alignment.topCenter,
                child: SizeTransition(
                  sizeFactor: curved,
                  alignment: Alignment.topCenter,
                  child: FadeTransition(
                    opacity: curved,
                    child: ConstrainedBox(
                      constraints: BoxConstraints(maxHeight: resolvedMax),
                      child: Material(
                        type: MaterialType.transparency,
                        child: themes.wrap(builder(ctx)),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    ),
  );
}
