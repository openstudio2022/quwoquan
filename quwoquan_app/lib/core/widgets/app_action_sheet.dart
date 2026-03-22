import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';

class AppActionSheetItem<T> {
  const AppActionSheetItem({
    required this.label,
    this.value,
    this.description,
    this.icon,
    this.isSelected = false,
    this.isDestructive = false,
    this.enabled = true,
  });

  final String label;
  final T? value;
  final String? description;
  final IconData? icon;
  final bool isSelected;
  final bool isDestructive;
  final bool enabled;
}

class AppActionSheetSection<T> {
  const AppActionSheetSection({required this.items});

  final List<AppActionSheetItem<T>> items;
}

Future<T?> showAppActionSheet<T>(
  BuildContext context, {
  String? title,
  String? message,
  required List<AppActionSheetSection<T>> sections,
  String cancelLabel = UITextConstants.cancel,
  double? maxHeightRatio,
}) {
  return showCupertinoModalPopup<T>(
    context: context,
    barrierColor: Colors.transparent,
    builder: (sheetContext) => _AppActionSheet<T>(
      title: title,
      message: message,
      sections: sections,
      cancelLabel: cancelLabel,
      maxHeightRatio: maxHeightRatio,
    ),
  );
}

class _AppActionSheet<T> extends StatelessWidget {
  const _AppActionSheet({
    required this.sections,
    required this.cancelLabel,
    this.title,
    this.message,
    this.maxHeightRatio,
  });

  final String? title;
  final String? message;
  final List<AppActionSheetSection<T>> sections;
  final String cancelLabel;
  final double? maxHeightRatio;

  @override
  Widget build(BuildContext context) {
    final isDark =
        (CupertinoTheme.of(context).brightness ??
            MediaQuery.platformBrightnessOf(context)) ==
        Brightness.dark;
    final pageBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final cardBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );

    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      backgroundColor: pageBackground,
      maxHeightRatio: maxHeightRatio,
      contentPadding: const EdgeInsets.fromLTRB(
        AppSpacing.containerXs,
        0,
        AppSpacing.containerXs,
        AppSpacing.containerXs,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if ((title ?? '').trim().isNotEmpty ||
                (message ?? '').trim().isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  0,
                  AppSpacing.containerMd,
                  AppSpacing.interGroupSm,
                ),
                child: Column(
                  children: [
                    if ((title ?? '').trim().isNotEmpty)
                      SizedBox(
                        height: AppSpacing.modalHeaderHeight,
                        child: Center(
                          child: Text(
                            title!,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: AppTypography.lg,
                              fontWeight: AppTypography.semiBold,
                              color: primaryText,
                            ),
                          ),
                        ),
                      ),
                    if ((message ?? '').trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(
                          bottom: AppSpacing.interGroupSm,
                        ),
                        child: Text(
                          message!,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: secondaryText,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            for (final section in sections) ...[
              _ActionSheetSectionCard<T>(
                section: section,
                backgroundColor: cardBackground,
                dividerColor: divider,
                primaryText: primaryText,
                secondaryText: secondaryText,
              ),
              const SizedBox(height: AppSpacing.interGroupSm),
            ],
            Container(
              decoration: BoxDecoration(
                color: cardBackground,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: CupertinoButton(
                padding: const EdgeInsets.symmetric(
                  vertical: AppSpacing.containerSm,
                ),
                onPressed: () => Navigator.of(context).pop(),
                child: Text(
                  cancelLabel,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.medium,
                    color: secondaryText,
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

class _ActionSheetSectionCard<T> extends StatelessWidget {
  const _ActionSheetSectionCard({
    required this.section,
    required this.backgroundColor,
    required this.dividerColor,
    required this.primaryText,
    required this.secondaryText,
  });

  final AppActionSheetSection<T> section;
  final Color backgroundColor;
  final Color dividerColor;
  final Color primaryText;
  final Color secondaryText;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Column(
        children: section.items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final actionColor = item.isDestructive
              ? AppColors.iosDestructive(context)
              : primaryText;

          return Column(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: !item.enabled
                    ? null
                    : () => Navigator.of(context).pop(item.value),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.containerSm,
                  ),
                  child: Row(
                    children: [
                      if (item.icon != null) ...[
                        Icon(
                          item.icon,
                          size: AppSpacing.twenty,
                          color: actionColor,
                        ),
                        const SizedBox(width: AppSpacing.containerSm),
                      ],
                      Expanded(
                        child: Text(
                          item.label,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: item.isSelected
                                ? AppTypography.semiBold
                                : AppTypography.medium,
                            color: item.enabled
                                ? actionColor
                                : secondaryText.withValues(alpha: 0.55),
                          ),
                        ),
                      ),
                      if ((item.description ?? '').trim().isNotEmpty)
                        Flexible(
                          child: Text(
                            item.description!,
                            textAlign: TextAlign.right,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              color: item.isDestructive
                                  ? actionColor.withValues(alpha: 0.75)
                                  : secondaryText,
                            ),
                          ),
                        ),
                      if (item.isSelected) ...[
                        const SizedBox(width: AppSpacing.intraGroupSm),
                        Icon(
                          CupertinoIcons.check_mark,
                          size: AppSpacing.iconSmall,
                          color: AppColors.primaryColor,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              if (index < section.items.length - 1)
                Container(
                  height: AppSpacing.hairline,
                  margin: EdgeInsets.only(
                    left: item.icon == null
                        ? AppSpacing.containerMd
                        : AppSpacing.containerMd +
                              AppSpacing.twenty +
                              AppSpacing.containerSm,
                    right: AppSpacing.containerMd,
                  ),
                  color: dividerColor.withValues(alpha: 0.9),
                ),
            ],
          );
        }).toList(),
      ),
    );
  }
}
