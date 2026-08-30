import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 统一的 iOS 风格页面骨架
class AppScaffold extends StatelessWidget {
  const AppScaffold({
    super.key,
    this.child,
    this.body,
    this.navigationBar,
    this.backgroundColor,
    this.resizeToAvoidBottomInset = true,
  }) : assert(
         child != null || body != null,
         'AppScaffold requires either child or body.',
       ),
       assert(
         child == null || body == null,
         'AppScaffold accepts only one of child or body.',
       );

  final Widget? child;
  final Widget? body;
  final ObstructingPreferredSizeWidget? navigationBar;
  final Color? backgroundColor;
  final bool resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      navigationBar: navigationBar,
      backgroundColor: backgroundColor,
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
      // Several pages render Material-style text/actions inside a Cupertino
      // scaffold. A transparent Material host avoids debug-mode fallback text
      // emphasis/underline artifacts on those pages.
      child: Material(type: MaterialType.transparency, child: child ?? body!),
    );
  }
}

/// 统一的 iOS 风格导航栏
class AppNavigationBar extends StatelessWidget
    implements ObstructingPreferredSizeWidget {
  const AppNavigationBar({
    super.key,
    this.middle,
    this.leading,
    this.trailing,
    this.backgroundColor,
    this.border,
    this.previousPageTitle,
    this.automaticallyImplyLeading = true,
  });

  final Widget? middle;
  final Widget? leading;
  final Widget? trailing;
  final Color? backgroundColor;
  final Border? border;
  final String? previousPageTitle;
  final bool automaticallyImplyLeading;

  @override
  Widget build(BuildContext context) {
    return CupertinoNavigationBar(
      middle: middle,
      leading: leading,
      trailing: trailing,
      backgroundColor: backgroundColor,
      border: border,
      previousPageTitle: previousPageTitle,
      automaticallyImplyLeading: automaticallyImplyLeading,
    );
  }

  @override
  Size get preferredSize =>
      const Size.fromHeight(AppSpacing.appChromeNavigationBarHeight);

  @override
  bool shouldFullyObstruct(BuildContext context) {
    final backgroundColor =
        this.backgroundColor ?? CupertinoTheme.of(context).barBackgroundColor;
    return (backgroundColor.a * 255.0).round().clamp(0, 255) == 0xFF;
  }
}

/// 与聊天信息页一致的顶栏图标按钮：44 最小触控区 + [AppNavigationSemanticConstants.barIconSize] + 主标签色。
class AppNavigationBarIconButton extends StatelessWidget {
  const AppNavigationBarIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.color,
    this.surface = AppChromeSurface.standard,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final Color? color;

  /// chrome 表面语义：`immersive` 取无底色白色图标加柔和投影（REQ-019），
  /// 浅色媒体与失败面浅背景上仍可见；颜色与投影决策收口在
  /// [AppNavigationSemanticConstants]，调用方不再自管颜色。
  final AppChromeSurface surface;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = AppNavigationSemanticConstants.chromeActionBackground(
      surface: surface,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      minimumSize: Size(
        AppSpacing.appChromeActionButtonSize,
        AppSpacing.appChromeActionButtonSize,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(color: background, shape: BoxShape.circle),
        child: SizedBox(
          width: AppSpacing.appChromeActionButtonSize,
          height: AppSpacing.appChromeActionButtonSize,
          child: Center(
            child: Icon(
              icon,
              size: AppSpacing.appChromeActionIconSize,
              color:
                  color ??
                  AppNavigationSemanticConstants.chromeActionIconColor(
                    isDark,
                    surface: surface,
                  ),
              shadows: AppNavigationSemanticConstants.chromeActionIconShadows(
                surface: surface,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppNavigationBarTextAction extends StatelessWidget {
  const AppNavigationBarTextAction({
    super.key,
    required this.label,
    required this.onPressed,
    this.enabled = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final color = enabled
        ? AppNavigationSemanticConstants.barIconColor(isDark)
        : CupertinoColors.systemGrey.resolveFrom(context);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.appChromeTextActionHorizontalPadding,
      ),
      minimumSize: const Size(
        AppSpacing.appChromeActionButtonSize,
        AppSpacing.appChromeTextActionMinHeight,
      ),
      onPressed: enabled ? onPressed : null,
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: AppTypography.iosNavTitle,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}
