import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/test_keys.dart';

const Duration _kAppBottomModalTransitionDuration = Duration(milliseconds: 280);
const Duration _kAppBottomModalReverseDuration = Duration(milliseconds: 220);
const Duration _kAppDialogTransitionDuration = Duration(milliseconds: 220);

Future<T?> showAppBottomModal<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool barrierDismissible = true,
  bool useRootNavigator = true,
  RouteSettings? routeSettings,
}) {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final themes = InheritedTheme.capture(from: context, to: navigator.context);

  return navigator.push<T>(
    PageRouteBuilder<T>(
      settings: routeSettings,
      opaque: false,
      barrierDismissible: barrierDismissible,
      barrierColor: AppColors.transparent,
      barrierLabel: _modalBarrierLabel(context),
      transitionDuration: _kAppBottomModalTransitionDuration,
      reverseTransitionDuration: _kAppBottomModalReverseDuration,
      pageBuilder: (routeContext, animation, secondaryAnimation) {
        return themes.wrap(Builder(builder: builder));
      },
      transitionsBuilder: (routeContext, animation, secondaryAnimation, child) {
        final fade = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        final slide = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return Stack(
          fit: StackFit.expand,
          children: [
            FadeTransition(
              opacity: fade,
              child: const AppModalBrightnessLayer(),
            ),
            SlideTransition(
              key: TestKeys.appBottomModalSlideTransition,
              position: Tween<Offset>(
                begin: const Offset(0, 1),
                end: Offset.zero,
              ).animate(slide),
              child: child,
            ),
          ],
        );
      },
    ),
  );
}

Future<T?> showAppCupertinoDialog<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool barrierDismissible = false,
  bool useRootNavigator = true,
  RouteSettings? routeSettings,
}) {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final themes = InheritedTheme.capture(from: context, to: navigator.context);

  return navigator.push<T>(
    PageRouteBuilder<T>(
      settings: routeSettings,
      opaque: false,
      barrierDismissible: barrierDismissible,
      barrierColor: AppColors.transparent,
      barrierLabel: _modalBarrierLabel(context),
      transitionDuration: _kAppDialogTransitionDuration,
      reverseTransitionDuration: _kAppDialogTransitionDuration,
      pageBuilder: (routeContext, animation, secondaryAnimation) {
        return themes.wrap(
          SafeArea(
            child: Center(child: Builder(builder: builder)),
          ),
        );
      },
      transitionsBuilder: (routeContext, animation, secondaryAnimation, child) {
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return Stack(
          fit: StackFit.expand,
          children: [
            FadeTransition(
              opacity: curved,
              child: const AppModalBrightnessLayer(),
            ),
            FadeTransition(
              opacity: curved,
              child: ScaleTransition(
                key: TestKeys.appDialogScaleTransition,
                scale: Tween<double>(begin: 0.96, end: 1).animate(curved),
                child: child,
              ),
            ),
          ],
        );
      },
    ),
  );
}

Future<T?> showAppFloatingModal<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool barrierDismissible = true,
  bool useRootNavigator = true,
  RouteSettings? routeSettings,
  Duration transitionDuration = _kAppDialogTransitionDuration,
}) {
  final navigator = Navigator.of(context, rootNavigator: useRootNavigator);
  final themes = InheritedTheme.capture(from: context, to: navigator.context);

  return navigator.push<T>(
    PageRouteBuilder<T>(
      settings: routeSettings,
      opaque: false,
      barrierDismissible: barrierDismissible,
      barrierColor: AppColors.transparent,
      barrierLabel: _modalBarrierLabel(context),
      transitionDuration: transitionDuration,
      reverseTransitionDuration: transitionDuration,
      pageBuilder: (routeContext, animation, secondaryAnimation) {
        return themes.wrap(Builder(builder: builder));
      },
      transitionsBuilder: (routeContext, animation, secondaryAnimation, child) {
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return Stack(
          fit: StackFit.expand,
          children: [
            FadeTransition(
              opacity: curved,
              child: const AppModalBrightnessLayer(),
            ),
            FadeTransition(opacity: curved, child: child),
          ],
        );
      },
    ),
  );
}

Future<void> dismissAppModalAndRun(
  BuildContext modalContext, {
  required FutureOr<void> Function() action,
  Duration settleDelay = _kAppBottomModalReverseDuration,
}) async {
  if (!modalContext.mounted) {
    return;
  }
  Navigator.of(modalContext).pop();
  await Future<void>.delayed(settleDelay);
  await WidgetsBinding.instance.endOfFrame;
  await action();
}

class AppModalBrightnessLayer extends StatelessWidget {
  const AppModalBrightnessLayer({super.key, this.color});

  final Color? color;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    return IgnorePointer(
      child: ColoredBox(
        key: TestKeys.appModalBrightnessLayer,
        color:
            color ?? AppColorsFunctional.getColor(isDark, ColorType.modalScrim),
      ),
    );
  }
}

String _modalBarrierLabel(BuildContext context) {
  final cupertino = Localizations.of<CupertinoLocalizations>(
    context,
    CupertinoLocalizations,
  );
  if (cupertino != null) {
    return cupertino.modalBarrierDismissLabel;
  }
  final material = Localizations.of<MaterialLocalizations>(
    context,
    MaterialLocalizations,
  );
  return material?.modalBarrierDismissLabel ?? 'Dismiss';
}
