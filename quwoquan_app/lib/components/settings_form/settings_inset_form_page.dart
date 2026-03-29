import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

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
    this.trailing,
    this.resizeToAvoidBottomInset = true,
  });

  final bool isDark;
  final String title;
  final VoidCallback onBack;
  final Widget body;
  final Widget? trailing;
  final bool resizeToAvoidBottomInset;

  @override
  Widget build(BuildContext context) {
    final barBg =
        SettingsSemanticConstants.insetFormNavigationBarBackground(isDark);
    final borderColor =
        SettingsSemanticConstants.insetFormNavigationBarBorderColor(isDark);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SettingsSemanticConstants.pageChromeOverlayStyle(isDark),
      child: AppScaffold(
        backgroundColor:
            SettingsSemanticConstants.insetFormPageBackground(isDark),
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
          middle: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
          ),
          trailing: trailing == null
              ? null
              : IconTheme.merge(
                  data: IconThemeData(
                    color: AppNavigationSemanticConstants.barIconColor(isDark),
                    size: AppNavigationSemanticConstants.barIconSize,
                  ),
                  child: trailing!,
                ),
        ),
        body: body,
      ),
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
    final surface =
        SettingsSemanticConstants.insetFormSectionSurface(isDark);
    final radius =
        SettingsSemanticConstants.insetFormSectionCornerRadius;
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
  const SettingsInsetFormSectionDivider({super.key, required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final c = SettingsSemanticConstants.insetFormSectionDividerColor(isDark);
    return Container(
      height: AppSpacing.hairline,
      color: c,
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
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppSpacing.minInteractiveSize,
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
    );
  }
}
