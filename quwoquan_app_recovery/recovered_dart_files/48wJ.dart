import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/design_system/tokens/design_tokens.dart' as tokens;
import 'package:quwoquan_app/core/resources/app_strings.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_config.dart';
import 'more_action_responsive.dart';
import 'more_action_types.dart';
import 'more_action_utils.dart';

/// 通用更多功能弹窗组件
/// 支持动态配置、样式定制、国际化和权限控制
class MoreActionPopup extends ConsumerWidget {
  final MoreActionConfig config;
  final bool showDragHandle;
  final bool isScrollControlled;
  final VoidCallback? onClose;

  const MoreActionPopup({
    super.key,
    required this.config,
    this.showDragHandle = true,
    this.isScrollControlled = true,
    this.onClose,
  });

  /// 显示更多功能弹窗
  static Future<void> show({
    required BuildContext context,
    required MoreActionConfig config,
    bool showDragHandle = true,
    bool isScrollControlled = true,
    VoidCallback? onClose,
  }) {
    return showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: isScrollControlled,
      builder: (context) => MoreActionPopup(
        config: config,
        showDragHandle: showDragHandle,
        isScrollControlled: isScrollControlled,
        onClose: onClose,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final responsive = ref.watch(responsiveProvider);
    
    return Container(
      decoration: BoxDecoration(
        color: isDark
            ? config.style.backgroundColorDark ?? AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary)
            : config.style.backgroundColorLight ?? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(config.style.borderRadius ?? 20.r),
          topRight: Radius.circular(config.style.borderRadius ?? 20.r),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 拖拽指示器
          if (showDragHandle) _buildDragHandle(context, isDark),
          
          // 标题
          if (config.title.isNotEmpty) _buildTitle(context, isDark),
          
          // 横向功能列表
          if (config.horizontalItems.isNotEmpty) 
            _buildHorizontalActions(context, isDark, responsive),
          
          // 底部操作区域
          if (config.bottomActions.isNotEmpty) 
            _buildBottomActions(context, isDark, responsive),
        ],
      ),
    );
  }

  /// 构建拖拽指示器
  Widget _buildDragHandle(BuildContext context, bool isDark) {
    return Container(
      width: MoreActionResponsive.getModalDragHandleWidth(context),
      height: MoreActionResponsive.getModalDragHandleHeight(context),
      margin: EdgeInsets.only(
        top: context.safeGetContainerSpacing(SpacingSize.sm),
        bottom: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
        borderRadius: BorderRadius.circular(2.r),
      ),
    );
  }

  /// 构建标题
  Widget _buildTitle(BuildContext context, bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: context.safeGetContainerSpacing(SpacingSize.md),
        vertical: context.safeGetInterGroupSpacing(SpacingSize.sm),
      ),
      child: Text(
        config.title,
        style: TextStyle(
          fontSize: MoreActionResponsive.getModalTitleFontSize(context),
          fontWeight: FontWeight.bold,
          color: isDark
              ? config.style.titleColorDark ?? AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)
              : config.style.titleColorLight ?? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
        ),
      ),
    );
  }

  /// 构建横向功能列表
  Widget _buildHorizontalActions(BuildContext context, bool isDark, dynamic responsive) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.safeGetContainerSpacing(SpacingSize.md),
      ),
      child: Wrap(
        alignment: WrapAlignment.start,
        spacing: context.safeGetIntraGroupSpacing(SpacingSize.xs),
        runSpacing: context.safeGetIntraGroupSpacing(SpacingSize.xs),
        children: config.horizontalItems.map((item) {
          // 检查权限
          if (!MoreActionUtils.checkPermission(item.permission)) {
            return const SizedBox.shrink();
          }
          
          return _buildHorizontalActionItem(context, isDark, item);
        }).toList(),
      ),
    );
  }

  /// 构建横向功能项
  Widget _buildHorizontalActionItem(BuildContext context, bool isDark, MoreActionItem item) {
    return GestureDetector(
      onTap: () {
        Navigator.pop(context);
        item.onTap();
        onClose?.call();
      },
      child: Container(
        width: MoreActionResponsive.getModalItemWidth(context),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // 图标背景
            Container(
              width: MoreActionResponsive.getModalItemSize(context),
              height: MoreActionResponsive.getModalItemSize(context),
              decoration: BoxDecoration(
                color: isDark
                    ? config.style.itemBackgroundColorDark ?? AppColors.dark.backgroundSecondary
                    : config.style.itemBackgroundColorLight ?? AppColors.light.backgroundPrimary,
                borderRadius: BorderRadius.circular(config.style.itemBorderRadius ?? 8.r),
              ),
              child: Icon(
                item.icon ?? item.type.defaultIcon,
                size: MoreActionResponsive.getModalItemIconSize(context),
                color: isDark
                    ? config.style.iconColorDark ?? AppColors.dark.foregroundPrimary
                    : config.style.iconColorLight ?? AppColors.light.foregroundPrimary,
              ),
            ),
            SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            // 文字标签
            Text(
              item.title ?? item.type.defaultTitle,
              style: TextStyle(
                color: isDark
                    ? config.style.textColorDark ?? AppColors.dark.foregroundPrimary
                    : config.style.textColorLight ?? AppColors.light.foregroundPrimary,
                fontSize: MoreActionResponsive.getModalItemFontSize(context),
                fontWeight: FontWeight.w500,
              ),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  /// 构建底部操作区域
  Widget _buildBottomActions(BuildContext context, bool isDark, dynamic responsive) {
    return Container(
      margin: EdgeInsets.only(
        left: context.safeGetContainerSpacing(SpacingSize.md),
        right: context.safeGetContainerSpacing(SpacingSize.md),
        top: context.safeGetInterGroupSpacing(SpacingSize.sm),
        bottom: _getBottomPadding(context),
      ),
      decoration: BoxDecoration(
        color: isDark
            ? config.style.bottomBackgroundColorDark ?? AppColors.dark.backgroundSecondary
            : config.style.bottomBackgroundColorLight ?? AppColors.light.backgroundPrimary,
        borderRadius: BorderRadius.circular(config.style.bottomBorderRadius ?? 12.r),
      ),
      child: Column(
        children: config.bottomActions.map((action) {
          // 检查权限
          if (!MoreActionUtils.checkPermission(action.permission)) {
            return const SizedBox.shrink();
          }
          
          return _buildBottomActionItem(context, isDark, action);
        }).toList(),
      ),
    );
  }

  /// 构建底部操作项
  Widget _buildBottomActionItem(BuildContext context, bool isDark, MoreActionItem action) {
    return GestureDetector(
      onTap: () {
        Navigator.pop(context);
        action.onTap();
        onClose?.call();
      },
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: context.safeGetContainerSpacing(SpacingSize.md),
          vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              action.title ?? action.type.defaultTitle,
              style: TextStyle(
                color: isDark
                    ? config.style.bottomTextColorDark ?? AppColors.dark.foregroundInverse
                    : config.style.bottomTextColorLight ?? AppColors.light.foregroundPrimary,
                fontSize: MoreActionResponsive.getModalItemFontSize(context),
                fontWeight: FontWeight.w500,
              ),
            ),
            if (action.subtitle != null)
              Text(
                action.subtitle!,
                style: TextStyle(
                  color: isDark
                      ? config.style.bottomSubtitleColorDark ?? AppColors.dark.foregroundSecondary
                      : config.style.bottomSubtitleColorLight ?? AppColors.light.foregroundSecondary,
                  fontSize: MoreActionResponsive.getModalItemFontSize(context) * 0.9,
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// 获取平台适配的底部间距
  double _getBottomPadding(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    final platform = Theme.of(context).platform;
    
    if (platform == TargetPlatform.iOS) {
      return bottomPadding + 20.h;
    } else {
      return bottomPadding + 16.h;
    }
  }
}
