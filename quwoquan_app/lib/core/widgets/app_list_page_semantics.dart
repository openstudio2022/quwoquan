import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

const Duration _listPageStateTransitionDuration = Duration(milliseconds: 180);

enum AppListPageKind { multiOptionList, singleList }

class AppSegmentedChoiceItem<T extends Object> {
  const AppSegmentedChoiceItem({required this.value, required this.label});

  final T value;
  final String label;
}

class AppListPageScaffold extends StatelessWidget {
  const AppListPageScaffold({
    super.key,
    required this.isDark,
    required this.body,
    this.kind = AppListPageKind.singleList,
    this.title,
    this.onBack,
    this.middle,
    this.trailing,
    this.resizeToAvoidBottomInset = true,
  });

  final bool isDark;
  final Widget body;
  final AppListPageKind kind;
  final String? title;
  final VoidCallback? onBack;
  final Widget? middle;
  final Widget? trailing;
  final bool resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    final background = SettingsSemanticConstants.insetFormPageBackground(
      isDark,
    );
    final barBg = SettingsSemanticConstants.insetFormNavigationBarBackground(
      isDark,
    );
    final borderColor =
        SettingsSemanticConstants.insetFormNavigationBarBorderColor(isDark);
    final hasNavigation = title != null || middle != null || onBack != null;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SettingsSemanticConstants.pageChromeOverlayStyle(isDark),
      child: AppScaffold(
        backgroundColor: background,
        resizeToAvoidBottomInset: resizeToAvoidBottomInset,
        navigationBar: hasNavigation
            ? AppNavigationBar(
                automaticallyImplyLeading: false,
                backgroundColor: barBg,
                border: Border(
                  bottom: BorderSide(
                    color: borderColor,
                    width: AppSpacing.hairline,
                  ),
                ),
                leading: onBack == null
                    ? null
                    : AppNavigationBarIconButton(
                        icon: CupertinoIcons.back,
                        onPressed: onBack,
                      ),
                middle:
                    middle ??
                    Text(
                      title ?? '',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppNavigationSemanticConstants.barTitleTextStyle(
                        isDark,
                      ),
                    ),
                trailing: trailing,
              )
            : null,
        body: body,
      ),
    );
  }
}

class AppSegmentedChoiceBar<T extends Object> extends StatelessWidget {
  const AppSegmentedChoiceBar({
    super.key,
    required this.items,
    required this.selectedValue,
    required this.onChanged,
    this.maxWidth,
  });

  final List<AppSegmentedChoiceItem<T>> items;
  final T selectedValue;
  final ValueChanged<T> onChanged;
  final double? maxWidth;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = AppColors.iosSecondaryFill(
      context,
    ).withValues(alpha: isDark ? 0.35 : 0.70);
    final divider = SettingsSemanticConstants.insetFormSectionDividerColor(
      isDark,
    );
    final width = maxWidth ?? AppSpacing.minInteractiveSize * items.length * 2;
    return ConstrainedBox(
      constraints: BoxConstraints(
        minHeight: AppSpacing.minInteractiveSize,
        maxWidth: width,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: background,
            border: Border.all(color: divider, width: AppSpacing.hairline),
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          ),
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.hairline * 2),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (var index = 0; index < items.length; index++) ...[
                  Expanded(child: _buildItem(context, items[index], isDark)),
                  if (index < items.length - 1)
                    _SegmentDivider(
                      visible:
                          items[index].value != selectedValue &&
                          items[index + 1].value != selectedValue,
                      color: divider,
                    ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildItem(
    BuildContext context,
    AppSegmentedChoiceItem<T> item,
    bool isDark,
  ) {
    final selected = item.value == selectedValue;
    final labelColor = selected
        ? SettingsSemanticConstants.labelColor(isDark)
        : SettingsSemanticConstants.secondaryColor(isDark);
    return Semantics(
      button: true,
      selected: selected,
      child: AnimatedContainer(
        duration: _listPageStateTransitionDuration,
        curve: Curves.easeOutCubic,
        decoration: BoxDecoration(
          color: selected
              ? SettingsSemanticConstants.insetFormSectionSurface(isDark)
              : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          boxShadow: selected
              ? <BoxShadow>[
                  BoxShadow(
                    color: AppColors.black.withValues(
                      alpha: isDark ? 0.24 : 0.10,
                    ),
                    blurRadius: AppSpacing.xs,
                    offset: Offset(0, AppSpacing.hairline * 2),
                  ),
                ]
              : null,
        ),
        child: CupertinoButton(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          minimumSize: const Size(
            AppSpacing.minInteractiveSize,
            AppSpacing.minInteractiveSize,
          ),
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          onPressed: selected ? () {} : () => onChanged(item.value),
          child: Text(
            item.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: selected
                  ? AppTypography.semiBold
                  : AppTypography.medium,
              color: labelColor,
            ),
          ),
        ),
      ),
    );
  }
}

class AppListSurface extends StatelessWidget {
  const AppListSurface({
    super.key,
    required this.child,
    this.padding,
    this.border,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final bool? border;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = SettingsSemanticConstants.insetFormSectionSurface(isDark);
    final shouldBorder = border ?? isDark;
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        SettingsSemanticConstants.insetFormSectionCornerRadius,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          border: shouldBorder
              ? Border.all(
                  color: SettingsSemanticConstants.insetFormSectionDividerColor(
                    isDark,
                  ),
                  width: AppSpacing.hairline,
                )
              : null,
          borderRadius: BorderRadius.circular(
            SettingsSemanticConstants.insetFormSectionCornerRadius,
          ),
        ),
        child: Padding(padding: padding ?? EdgeInsets.zero, child: child),
      ),
    );
  }
}

class AppListRowCard extends StatelessWidget {
  const AppListRowCard({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return AppListSurface(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerSm),
      child: child,
    );
  }
}

class _SegmentDivider extends StatelessWidget {
  const _SegmentDivider({required this.visible, required this.color});

  final bool visible;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: _listPageStateTransitionDuration,
      opacity: visible ? 1 : 0,
      child: Container(
        width: AppSpacing.hairline,
        height: AppSpacing.buttonHeightSm,
        color: color,
      ),
    );
  }
}
