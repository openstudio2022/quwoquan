import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

class AppBottomModalSurface extends StatelessWidget {
  const AppBottomModalSurface({
    super.key,
    required this.child,
    required this.onDismiss,
    this.backgroundColor,
    this.contentPadding = EdgeInsets.zero,
    this.maxHeightRatio,
    this.showHandle = true,
    this.panelKey,
  });

  final Widget child;
  final VoidCallback onDismiss;
  final Color? backgroundColor;
  final EdgeInsetsGeometry contentPadding;
  final double? maxHeightRatio;
  final bool showHandle;
  final Key? panelKey;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final maxHeight =
        MediaQuery.sizeOf(context).height *
        (maxHeightRatio ?? AppSpacing.modalSheetMaxHeightRatio);
    final sheetBackground =
        backgroundColor ??
        AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated);
    final handleColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorOpaque,
    );

    return Material(
      type: MaterialType.transparency,
      child: SizedBox.expand(
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onDismiss,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.modalScrim,
                    ),
                  ),
                ),
              ),
            ),
            Align(
              alignment: Alignment.bottomCenter,
              child: Padding(
                padding: EdgeInsets.only(
                  left: MediaQuery.viewPaddingOf(context).left,
                  right: MediaQuery.viewPaddingOf(context).right,
                ),
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {},
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(
                      maxWidth: AppSpacing.feedMaxContentWidth,
                    ),
                    child: ConstrainedBox(
                      constraints: BoxConstraints(maxHeight: maxHeight),
                      child: Container(
                        key: panelKey,
                        decoration: BoxDecoration(
                          color: sheetBackground,
                          borderRadius: const BorderRadius.vertical(
                            top: Radius.circular(AppSpacing.largeBorderRadius),
                          ),
                        ),
                        child: Padding(
                          padding: contentPadding.add(
                            EdgeInsets.only(
                              bottom: MediaQuery.viewPaddingOf(context).bottom,
                            ),
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              if (showHandle) ...[
                                SizedBox(height: AppSpacing.intraGroupSm),
                                Center(
                                  child: Container(
                                    width:
                                        AppSpacing.createEntrySheetHandleWidth,
                                    height:
                                        AppSpacing.createEntrySheetHandleHeight,
                                    decoration: BoxDecoration(
                                      color: handleColor,
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.createEntrySheetHandleHeight,
                                      ),
                                    ),
                                  ),
                                ),
                                SizedBox(height: AppSpacing.interGroupSm),
                              ],
                              Flexible(fit: FlexFit.loose, child: child),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AppTopModalSurface extends StatelessWidget {
  const AppTopModalSurface({
    super.key,
    required this.child,
    required this.onDismiss,
    this.backgroundColor,
    this.backdropColor,
    this.backdropBlurSigma,
    this.contentPadding = EdgeInsets.zero,
    this.maxHeightRatio,
    this.panelKey,
  });

  final Widget child;
  final VoidCallback onDismiss;
  final Color? backgroundColor;
  final Color? backdropColor;
  final double? backdropBlurSigma;
  final EdgeInsetsGeometry contentPadding;
  final double? maxHeightRatio;
  final Key? panelKey;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final maxHeight =
        MediaQuery.sizeOf(context).height *
        (maxHeightRatio ?? AppSpacing.modalSheetMaxHeightRatio);
    final sheetBackground =
        backgroundColor ??
        AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorOpaque,
    ).withValues(alpha: isDark ? 0.28 : 0.18);
    final shadowColor = AppColors.black.withValues(alpha: isDark ? 0.18 : 0.08);
    final resolvedBackdropColor =
        backdropColor ??
        AppColorsFunctional.getColor(
          isDark,
          ColorType.modalScrim,
        ).withValues(alpha: isDark ? 0.06 : 0.03);
    final resolvedBackdropBlurSigma = backdropBlurSigma ?? AppSpacing.sm / 2;

    return Material(
      type: MaterialType.transparency,
      child: SizedBox.expand(
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onDismiss,
                child: BackdropFilter(
                  filter: ui.ImageFilter.blur(
                    sigmaX: resolvedBackdropBlurSigma,
                    sigmaY: resolvedBackdropBlurSigma,
                  ),
                  child: ColoredBox(color: resolvedBackdropColor),
                ),
              ),
            ),
            Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: EdgeInsets.only(
                  left: MediaQuery.viewPaddingOf(context).left,
                  right: MediaQuery.viewPaddingOf(context).right,
                ),
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {},
                  child: SizedBox(
                    width: double.infinity,
                    height: maxHeight,
                    child: Container(
                      key: panelKey,
                      decoration: BoxDecoration(
                        color: sheetBackground,
                        borderRadius: const BorderRadius.vertical(
                          bottom: Radius.circular(AppSpacing.largeBorderRadius),
                        ),
                        border: Border(
                          bottom: BorderSide(
                            color: borderColor,
                            width: AppSpacing.hairline,
                          ),
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: shadowColor,
                            blurRadius: AppSpacing.largeBorderRadius * 2,
                            offset: Offset(0, AppSpacing.containerSm),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: const BorderRadius.vertical(
                          bottom: Radius.circular(AppSpacing.largeBorderRadius),
                        ),
                        child: Padding(padding: contentPadding, child: child),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AppFullscreenModalSurface extends StatelessWidget {
  const AppFullscreenModalSurface({
    super.key,
    required this.child,
    this.backgroundColor,
    this.contentPadding = EdgeInsets.zero,
    this.surfaceKey,
  });

  final Widget child;
  final Color? backgroundColor;
  final EdgeInsetsGeometry contentPadding;
  final Key? surfaceKey;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;

    return Material(
      type: MaterialType.transparency,
      child: SizedBox.expand(
        key: surfaceKey,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color:
                backgroundColor ??
                AppColorsFunctional.getColor(isDark, ColorType.pageBackground),
          ),
          child: SafeArea(
            child: Padding(padding: contentPadding, child: child),
          ),
        ),
      ),
    );
  }
}
