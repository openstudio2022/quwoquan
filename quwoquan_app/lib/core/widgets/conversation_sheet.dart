import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 贴底对话态 Sheet：可选主标题（居中）+ 可选脚注（卡片上方、左对齐）。
class ConversationSheetHeader extends StatelessWidget {
  const ConversationSheetHeader({
    super.key,
    required this.isDark,
    this.title,
    this.footnote,
  });

  final bool isDark;
  final String? title;
  final String? footnote;

  @override
  Widget build(BuildContext context) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    final head = (title ?? '').trim();
    final foot = (footnote ?? '').trim();
    if (head.isEmpty && foot.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.blockHorizontalPadding,
        0,
        SettingsSemanticConstants.blockHorizontalPadding,
        SettingsSemanticConstants.conversationSheetSectionGap,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (head.isNotEmpty)
            SizedBox(
              height: AppSpacing.modalHeaderHeight,
              child: Center(
                child: Text(
                  head,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: primary,
                  ),
                ),
              ),
            ),
          if (head.isNotEmpty && foot.isNotEmpty)
            SizedBox(
              height: SettingsSemanticConstants
                  .conversationSheetTitleToFootnoteSpacing,
            ),
          if (foot.isNotEmpty)
            Text(
              foot,
              textAlign: head.isEmpty ? TextAlign.center : TextAlign.start,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.regular,
                color: secondary,
                height: AppTypography.lineHeightCompact,
              ),
            ),
        ],
      ),
    );
  }
}

/// 列表选项白卡片（圆角 + 可选描边）。
class ConversationSheetListCard extends StatelessWidget {
  const ConversationSheetListCard({
    super.key,
    required this.isDark,
    required this.child,
    this.useBorder = true,
  });

  final bool isDark;
  final Widget child;
  final bool useBorder;

  @override
  Widget build(BuildContext context) {
    final bg =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final radius =
        SettingsSemanticConstants.conversationSheetCardCornerRadius;
    final border =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(radius),
        border: useBorder ? Border.all(color: border) : null,
      ),
      child: child,
    );
  }
}

/// 行间 hairline；[dividerLeftInset] 为分割线左缘相对卡片内容区的缩进。
class ConversationSheetDivider extends StatelessWidget {
  const ConversationSheetDivider({
    super.key,
    required this.isDark,
    required this.dividerLeftInset,
  });

  final bool isDark;
  final double dividerLeftInset;

  @override
  Widget build(BuildContext context) {
    final d =
        SettingsSemanticConstants.conversationSheetDividerColor(isDark);
    return Container(
      height: AppSpacing.hairline,
      margin: EdgeInsets.only(
        left: dividerLeftInset,
        right: SettingsSemanticConstants.blockHorizontalPadding,
      ),
      color: d.withValues(alpha: 0.9),
    );
  }
}

/// 互斥单选行：可选 leading 图标、主文案、可选右侧说明、选中对勾。
class ConversationSheetSingleSelectRow extends StatelessWidget {
  const ConversationSheetSingleSelectRow({
    super.key,
    required this.isDark,
    required this.label,
    this.icon,
    this.description,
    this.isSelected = false,
    this.isDestructive = false,
    this.enabled = true,
    required this.onTap,
  });

  final bool isDark;
  final String label;
  final IconData? icon;
  final String? description;
  final bool isSelected;
  final bool isDestructive;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    final actionColor = isDestructive
        ? AppColors.iosDestructive(context)
        : primary;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: enabled ? onTap : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppSpacing.minInteractiveSize,
          ),
          child: Row(
            children: [
              if (icon != null) ...[
                Icon(
                  icon,
                  size: AppSpacing.twenty,
                  color: actionColor,
                ),
                const SizedBox(width: AppSpacing.containerSm),
              ],
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.medium,
                    color: enabled
                        ? actionColor
                        : secondary.withValues(alpha: 0.55),
                  ),
                ),
              ),
              if ((description ?? '').trim().isNotEmpty)
                Flexible(
                  child: Text(
                    description!.trim(),
                    textAlign: TextAlign.right,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: isDestructive
                          ? actionColor.withValues(alpha: 0.75)
                          : secondary,
                    ),
                  ),
                ),
              if (isSelected) ...[
                const SizedBox(width: AppSpacing.intraGroupSm),
                Icon(
                  CupertinoIcons.check_mark,
                  size: AppSpacing.iconSmall,
                  color: SettingsSemanticConstants.conversationSheetSelectionAccentColor(
                    isDark,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// 分割线左缩进（与首列文字对齐）。
  static double dividerInsetForIcon(bool hasIcon) {
    if (!hasIcon) return AppSpacing.containerMd;
    return AppSpacing.containerMd + AppSpacing.twenty + AppSpacing.containerSm;
  }
}

/// 左图标 + 主标题 + 可选右侧说明（无对勾）；用于帖子「更多功能」列表等。
class ConversationSheetActionRow extends StatelessWidget {
  const ConversationSheetActionRow({
    super.key,
    required this.isDark,
    required this.icon,
    required this.label,
    this.description,
    required this.onTap,
  });

  final bool isDark;
  final IconData icon;
  final String label;
  final String? description;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary =
        SettingsSemanticConstants.conversationSheetPrimaryLabelColor(isDark);
    final secondary =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppSpacing.minInteractiveSize,
          ),
          child: Row(
            children: [
              Icon(icon, size: AppSpacing.twenty, color: primary),
              const SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.regular,
                    color: primary,
                  ),
                ),
              ),
              if ((description ?? '').trim().isNotEmpty) ...[
                const SizedBox(width: AppSpacing.containerSm),
                Expanded(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Text(
                      description!.trim(),
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.medium,
                        color: secondary,
                      ),
                      textAlign: TextAlign.right,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  static double get dividerLeftInsetDefault =>
      AppSpacing.containerMd + AppSpacing.twenty;
}

/// 全宽取消条（与列表卡同宽、同圆角/描边）。
class ConversationSheetCancelBar extends StatelessWidget {
  const ConversationSheetCancelBar({
    super.key,
    required this.isDark,
    required this.label,
    required this.onTap,
    this.useBorder = true,
  });

  final bool isDark;
  final String label;
  final VoidCallback onTap;
  final bool useBorder;

  @override
  Widget build(BuildContext context) {
    final bg =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final border =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    final fg =
        SettingsSemanticConstants.conversationSheetSecondaryLabelColor(isDark);
    final radius =
        SettingsSemanticConstants.conversationSheetCardCornerRadius;

    return SizedBox(
      width: double.infinity,
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
          border: useBorder ? Border.all(color: border) : null,
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.buttonHeight,
            ),
            child: Center(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.medium,
                  color: fg,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 贴底对话态：同一列表卡内全宽「取消」+ hairline + 「确定」（主题蓝）。
class ConversationSheetCancelConfirmBar extends StatelessWidget {
  const ConversationSheetCancelConfirmBar({
    super.key,
    required this.isDark,
    required this.cancelLabel,
    required this.confirmLabel,
    required this.onCancel,
    required this.onConfirm,
    this.useBorder = true,
  });

  final bool isDark;
  final String cancelLabel;
  final String confirmLabel;
  final VoidCallback onCancel;
  final VoidCallback onConfirm;
  final bool useBorder;

  @override
  Widget build(BuildContext context) {
    final divider =
        SettingsSemanticConstants.conversationSheetDividerColor(isDark);
    return ConversationSheetListCard(
      isDark: isDark,
      useBorder: useBorder,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onCancel,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                minHeight: AppSpacing.buttonHeight,
              ),
              child: Center(
                child: Text(
                  cancelLabel,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.medium,
                    color: SettingsSemanticConstants
                        .conversationSheetSecondaryLabelColor(isDark),
                  ),
                ),
              ),
            ),
          ),
          Container(
            height: AppSpacing.hairline,
            width: double.infinity,
            color: divider.withValues(alpha: 0.9),
          ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onConfirm,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                minHeight: AppSpacing.buttonHeight,
              ),
              child: Center(
                child: Text(
                  confirmLabel,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
