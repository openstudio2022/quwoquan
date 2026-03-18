import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

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
      child: Material(
        type: MaterialType.transparency,
        child: child ?? body!,
      ),
    );
  }
}

/// 统一的 iOS 风格导航栏
class AppNavigationBar extends StatelessWidget implements ObstructingPreferredSizeWidget {
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
  Size get preferredSize => const Size.fromHeight(AppSpacing.toolbarHeight);

  @override
  bool shouldFullyObstruct(BuildContext context) {
    final backgroundColor =
        this.backgroundColor ?? CupertinoTheme.of(context).barBackgroundColor;
    return (backgroundColor.a * 255.0).round().clamp(0, 255) == 0xFF;
  }
}
