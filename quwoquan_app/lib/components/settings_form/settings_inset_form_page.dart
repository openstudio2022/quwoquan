import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

/// A/B 类设置全屏页共用：灰底、[insetFormNavigationBarBackground] 顶栏、
/// [AppNavigationBarIconButton] 返回与 hairline 底边。
Widget _settingsInsetPageChrome({
  required bool isDark,
  required String title,
  required VoidCallback onBack,
  required Widget body,
  Widget? middle,
  Widget? trailing,
  bool resizeToAvoidBottomInset = true,
}) {
  final barBg = SettingsSemanticConstants.insetFormNavigationBarBackground(
    isDark,
  );
  final borderColor =
      SettingsSemanticConstants.insetFormNavigationBarBorderColor(isDark);
  final trail = trailing;

  return AnnotatedRegion<SystemUiOverlayStyle>(
    value: SettingsSemanticConstants.pageChromeOverlayStyle(isDark),
    child: AppScaffold(
      backgroundColor: SettingsSemanticConstants.insetFormPageBackground(
        isDark,
      ),
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
      navigationBar: AppNavigationBar(
        automaticallyImplyLeading: false,
        backgroundColor: barBg,
        border: Border(
          bottom: BorderSide(color: borderColor, width: AppSpacing.hairline),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: onBack,
        ),
        middle:
            middle ??
            Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
            ),
        trailing: trail == null
            ? null
            : IconTheme.merge(
                data: IconThemeData(
                  color: AppNavigationSemanticConstants.barIconColor(isDark),
                  size: AppNavigationSemanticConstants.barIconSize,
                ),
                child: trail,
              ),
      ),
      body: body,
    ),
  );
}

/// 全屏 **Inset Grouped** 表单骨架：灰底 + 白（深模式深灰）分组卡片，对齐 iOS 设置页。
///
/// 顶栏背景与页面底同色；返回与操作图标使用 [SettingsSemanticConstants.insetFormNavigationBarActionIconColor]，避免默认 Cupertino 蓝。
class SettingsInsetFormPageScaffold extends StatelessWidget {
  const SettingsInsetFormPageScaffold({
    super.key,
    required this.isDark,
    required this.title,
    required this.onBack,
    required this.body,
    this.middle,
    this.trailing,
    this.resizeToAvoidBottomInset = true,
  });

  final bool isDark;
  final String title;
  final VoidCallback onBack;
  final Widget body;
  final Widget? middle;
  final Widget? trailing;
  final bool resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    return _settingsInsetPageChrome(
      isDark: isDark,
      title: title,
      onBack: onBack,
      body: body,
      middle: middle,
      trailing: trailing,
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
    );
  }
}

/// B 类：**成员选择 + 内嵌搜索** 全屏页，与 [SettingsInsetFormPageScaffold] **同源顶栏/灰底**。
///
/// 业务将搜索条与列表置于 [body]（通常为 `Column` + `Expanded(ListView)`）。
class SettingsInsetMemberPickerPageScaffold extends StatelessWidget {
  const SettingsInsetMemberPickerPageScaffold({
    super.key,
    required this.isDark,
    required this.title,
    required this.onBack,
    required this.body,
    this.middle,
    this.trailing,
    this.resizeToAvoidBottomInset = true,
  });

  final bool isDark;
  final String title;
  final VoidCallback onBack;
  final Widget body;
  final Widget? middle;
  final Widget? trailing;
  final bool resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    return _settingsInsetPageChrome(
      isDark: isDark,
      title: title,
      onBack: onBack,
      body: body,
      middle: middle,
      trailing: trailing,
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
    );
  }
}

/// Inset grouped 分组容器：无描边，靠与页面灰底对比形成「卡片」边缘（高品质 iOS）。
class SettingsInsetGroupedSection extends StatelessWidget {
  const SettingsInsetGroupedSection({
    super.key,
    required this.isDark,
    required this.child,
    this.header,
    this.density = SettingsInsetSectionDensity.standard,
  });

  final bool isDark;
  final Widget child;
  final String? header;
  final SettingsInsetSectionDensity density;

  @override
  Widget build(BuildContext context) {
    final surface = SettingsSemanticConstants.insetFormSectionSurface(isDark);
    final radius = SettingsSemanticConstants.insetFormSectionCornerRadius;
    final vertical = density == SettingsInsetSectionDensity.compact
        ? SettingsSemanticConstants.insetFormSectionPaddingVerticalCompact
        : SettingsSemanticConstants.insetFormSectionPaddingVerticalStandard;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (header != null && header!.trim().isNotEmpty)
          Padding(
            padding: EdgeInsets.only(
              left: SettingsSemanticConstants.blockHorizontalPadding,
              right: SettingsSemanticConstants.blockHorizontalPadding,
              bottom: AppSpacing.intraGroupSm,
            ),
            child: Text(
              header!,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.medium,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            ),
          ),
        ClipRRect(
          borderRadius: BorderRadius.circular(radius),
          child: ColoredBox(
            color: surface,
            child: Padding(
              padding: EdgeInsets.only(
                left: SettingsSemanticConstants.blockHorizontalPadding,
                right: SettingsSemanticConstants.blockHorizontalPadding,
                top: vertical,
                bottom: vertical,
              ),
              child: child,
            ),
          ),
        ),
      ],
    );
  }
}

enum SettingsInsetSectionDensity {
  /// 与帖子更多功能列表行高接近的紧凑内边距。
  compact,

  /// 成员网格等需要略多上下留白。
  standard,
}

/// 分组内水平分割线（hairline）。
class SettingsInsetFormSectionDivider extends StatelessWidget {
  const SettingsInsetFormSectionDivider({
    super.key,
    required this.isDark,
    this.leadingInset = AppSpacing.zero,
    this.trailingInset = AppSpacing.zero,
  });

  final bool isDark;
  final double leadingInset;
  final double trailingInset;

  @override
  Widget build(BuildContext context) {
    final c = SettingsSemanticConstants.insetFormSectionDividerColor(isDark);
    return Container(
      margin: EdgeInsets.only(left: leadingInset, right: trailingInset),
      height: AppSpacing.hairline,
      color: c,
    );
  }
}

class SettingsInsetTrailingText extends StatelessWidget {
  const SettingsInsetTrailingText({
    super.key,
    required this.isDark,
    required this.value,
  });

  final bool isDark;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Text(
      value,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.right,
      style: TextStyle(
        fontSize: AppTypography.iosSubheadline,
        fontWeight: AppTypography.regular,
        color: SettingsSemanticConstants.secondaryColor(isDark),
      ),
    );
  }
}

class SettingsInsetChevron extends StatelessWidget {
  const SettingsInsetChevron({super.key, required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Icon(
      CupertinoIcons.chevron_forward,
      size: SettingsSemanticConstants.insetFormRowChevronSize,
      color: SettingsSemanticConstants.secondaryColor(isDark),
    );
  }
}

class SettingsInsetNavigationRow extends StatelessWidget {
  const SettingsInsetNavigationRow({
    super.key,
    required this.isDark,
    required this.label,
    this.leadingIcon,
    this.trailingText,
    this.trailing,
    this.onTap,
    this.isDestructive = false,
    this.showChevron = true,
  });

  final bool isDark;
  final String label;
  final IconData? leadingIcon;
  final String? trailingText;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool isDestructive;
  final bool showChevron;

  @override
  Widget build(BuildContext context) {
    final labelColor = isDestructive
        ? AppColors.iosDestructive(context)
        : SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    final icon = leadingIcon;
    final value = trailingText?.trim();
    final hasChevron = showChevron && onTap != null;

    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
            ),
            child: Row(
              children: <Widget>[
                if (icon != null) ...<Widget>[
                  Icon(
                    icon,
                    size: SettingsSemanticConstants.insetFormRowIconSize,
                    color: secondaryColor,
                  ),
                  SizedBox(width: AppSpacing.containerSm),
                ],
                Expanded(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.regular,
                      color: labelColor,
                    ),
                  ),
                ),
                if (value != null && value.isNotEmpty) ...<Widget>[
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Flexible(
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: SettingsInsetTrailingText(
                        isDark: isDark,
                        value: value,
                      ),
                    ),
                  ),
                ],
                if (trailing != null) ...<Widget>[
                  SizedBox(width: AppSpacing.intraGroupSm),
                  trailing!,
                ],
                if (hasChevron) ...<Widget>[
                  SizedBox(
                    width:
                        SettingsSemanticConstants.insetFormTrailingChevronGap,
                  ),
                  SettingsInsetChevron(isDark: isDark),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 表单行：左标题 + 右 trailing；触控区与最小高度对齐系统习惯。
class SettingsInsetFormRow extends StatelessWidget {
  const SettingsInsetFormRow({
    super.key,
    required this.isDark,
    required this.label,
    required this.trailing,
    this.onTap,
  });

  final bool isDark;
  final String label;
  final Widget trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final labelColor = SettingsSemanticConstants.labelColor(isDark);
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.regular,
                      color: labelColor,
                    ),
                  ),
                ),
                trailing,
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 设置页同源：分组内居中操作行（切换账号、退出登录、退出群聊等）。
class SettingsInsetCenteredActionRow extends StatelessWidget {
  const SettingsInsetCenteredActionRow({
    super.key,
    required this.isDark,
    required this.label,
    required this.onTap,
    this.isDestructive = false,
  });

  final bool isDark;
  final String label;
  final VoidCallback onTap;
  final bool isDestructive;

  @override
  Widget build(BuildContext context) {
    final labelColor = isDestructive
        ? AppColors.iosDestructive(context)
        : SettingsSemanticConstants.labelColor(isDark);
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
            ),
            child: Center(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                  color: labelColor,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class SettingsInsetSwitchRow extends StatelessWidget {
  const SettingsInsetSwitchRow({
    super.key,
    required this.isDark,
    required this.label,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });

  final bool isDark;
  final String label;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final labelColor = SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    final sub = subtitle?.trim();
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () => onChanged(!value),
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: SettingsSemanticConstants.insetFormRowVerticalPadding,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: SettingsSemanticConstants.insetFormRowMinHeight,
            ),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosSubheadline,
                          fontWeight: AppTypography.regular,
                          color: labelColor,
                        ),
                      ),
                      if (sub != null && sub.isNotEmpty) ...<Widget>[
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          sub,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            fontWeight: AppTypography.regular,
                            height: AppSpacing.textLineHeightFootnote,
                            color: secondaryColor,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.containerMd),
                CupertinoSwitch(
                  value: value,
                  onChanged: onChanged,
                  activeTrackColor:
                      SettingsSemanticConstants.switchActiveTrackColor,
                  inactiveTrackColor:
                      SettingsSemanticConstants.switchInactiveTrackColor(
                        isDark,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class SettingsInsetChoiceRow extends StatelessWidget {
  const SettingsInsetChoiceRow({
    super.key,
    required this.isDark,
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  final bool isDark;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SettingsInsetNavigationRow(
      isDark: isDark,
      label: label,
      onTap: onTap,
      showChevron: false,
      trailing: isSelected
          ? Icon(
              CupertinoIcons.check_mark,
              size: AppSpacing.iconSmall,
              color: AppColors.primaryColor,
            )
          : null,
    );
  }
}
