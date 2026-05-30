import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 统一对象推荐卡的对象类型（人/地点事物/圈子/组织）。
/// 真相源 = [IntersectionReason.relationKind]（服务端），端不二次推断。
enum UnifiedObjectKind {
  person,
  place,
  circle,
  org;

  static UnifiedObjectKind fromRelationKind(String relationKind) {
    switch (relationKind) {
      case 'person':
      case 'user':
        return UnifiedObjectKind.person;
      case 'place':
      case 'poi':
      case 'location':
        return UnifiedObjectKind.place;
      case 'circle':
        return UnifiedObjectKind.circle;
      case 'org':
      case 'organization':
        return UnifiedObjectKind.org;
      default:
        return UnifiedObjectKind.person;
    }
  }
}

/// 统一对象推荐卡：人/地点事物/圈子/组织四类共用同一卡语言。
///
/// 只读消费 [IntersectionReason]：
/// - 主文案 = `displayText`（服务端交集句，端不本地拼装，G2）；
/// - 共同点计数 = `sharedCount`（仅数字格式化）；
/// - 行动动词 = `actionType`（映射动词，非交集句）；
/// - 对象类型 = `relationKind`（决定图标 / 路由）；跳转目标 = `actionTargetId`。
///
/// 导航与行动回流由父层提供（[onOpen] / [onAction]），本卡不直接路由/埋点，
/// 保持展示与行为解耦。无 `actionTargetId` 时由父层决定不展示。
class UnifiedObjectCard extends StatelessWidget {
  const UnifiedObjectCard({
    super.key,
    required this.reason,
    required this.isDark,
    this.onOpen,
    this.onAction,
  });

  final IntersectionReason reason;
  final bool isDark;
  final VoidCallback? onOpen;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final kind = UnifiedObjectKind.fromRelationKind(reason.relationKind);
    final accent = isDark ? AppColors.iosAccentDark : AppColors.primaryColor;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final primaryText = reason.displayText.trim().isNotEmpty
        ? reason.displayText.trim()
        : reason.label.trim();
    final sharedCountText = UITextConstants.homeObjectSharedCount(
      reason.sharedCount,
    );
    final actionLabel = UITextConstants.homeObjectActionLabel(reason.actionType);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onOpen,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minHeight: AppSpacing.minInteractiveSize,
          maxWidth: AppSpacing.homeObjectCardMaxWidth,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(
              color: accent.withValues(alpha: isDark ? 0.18 : 0.12),
              width: AppSpacing.hairline,
            ),
          ),
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerSm),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _KindAvatar(kind: kind, accent: accent, isDark: isDark),
                SizedBox(width: AppSpacing.intraGroupSm),
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        primaryText,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosSubheadline,
                          fontWeight: AppTypography.semiBold,
                          color: fg,
                          letterSpacing: -0.12,
                        ),
                      ),
                      if (sharedCountText.isNotEmpty) ...[
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          sharedCountText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosCaption1,
                            fontWeight: AppTypography.regular,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                _ActionButton(
                  label: actionLabel,
                  accent: accent,
                  isDark: isDark,
                  onPressed: onAction,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _KindAvatar extends StatelessWidget {
  const _KindAvatar({
    required this.kind,
    required this.accent,
    required this.isDark,
  });

  final UnifiedObjectKind kind;
  final Color accent;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSpacing.avatarUserSm,
      height: AppSpacing.avatarUserSm,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Icon(_icon, size: AppSpacing.eighteen, color: accent),
    );
  }

  IconData get _icon {
    switch (kind) {
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_crop_circle_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_3_fill;
      case UnifiedObjectKind.org:
        return CupertinoIcons.building_2_fill;
    }
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.accent,
    required this.isDark,
    this.onPressed,
  });

  final String label;
  final Color accent;
  final bool isDark;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      color: accent,
      onPressed: onPressed,
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.semiBold,
          color: AppColors.white,
          letterSpacing: -0.1,
        ),
      ),
    );
  }
}
