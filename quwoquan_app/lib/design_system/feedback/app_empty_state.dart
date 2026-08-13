import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 页面/区块级空态的唯一共享组件。
///
/// 与 `AppPageErrorState`（错误态）、`AppRequestFeedback`（加载态）同属
/// 反馈层三态积木；页面不得再各自实现私有 `_XxxEmptyState`。颜色全部走
/// context 动态色，深浅色自动适配，无需传 isDark。
///
/// - 整页空态：直接放入页面主体（自带 Center + 容器留白）。
/// - 区块内嵌空态：外层自行控制约束即可。
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    this.icon,
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
    this.actionKey,
  });

  /// 可选插图图标；feed 内嵌空态（融入内容流、无图标）传 null。
  final IconData? icon;
  final String title;
  final String? subtitle;

  /// 可选主动作（如「去逛逛」「立即创建」）；label 与回调必须成对出现。
  final String? actionLabel;
  final VoidCallback? onAction;

  /// 主动作按钮的 widget key（供测试与遥测定位）。
  final Key? actionKey;

  @override
  Widget build(BuildContext context) {
    final secondaryLabel = AppColors.iosSecondaryLabel(context);
    final hasSubtitle = (subtitle ?? '').trim().isNotEmpty;
    final hasAction = (actionLabel ?? '').trim().isNotEmpty && onAction != null;
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (icon != null) ...<Widget>[
              Icon(icon, size: AppSpacing.iconLarge, color: secondaryLabel),
              SizedBox(height: AppSpacing.interGroupMd),
            ],
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            if (hasSubtitle) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                subtitle!.trim(),
                textAlign: TextAlign.center,
                style: TextStyle(
                  // 正文级次级说明必须满足 WCAG AA 4.5:1（OPEN-003 实测
                  // secondaryLabel 浅色底仅约 3.4:1）。
                  color: AppColors.secondaryLabelAccessible(context),
                  fontSize: AppTypography.iosSubheadline,
                  height: AppSpacing.textLineHeightBody,
                ),
              ),
            ],
            if (hasAction) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupMd),
              CupertinoButton(
                key: actionKey,
                // 触控热区下限 44×44（规则 §2.4），CTA 不得低于最小可交互尺寸。
                minimumSize: const Size(
                  AppSpacing.minInteractiveSize,
                  AppSpacing.minInteractiveSize,
                ),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                color: AppColors.iosAccent(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
                onPressed: onAction,
                child: Text(
                  actionLabel!.trim(),
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
