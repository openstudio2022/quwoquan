import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 对象页元信息胶囊（类型 / 状态 / 标签），主页摘要卡与实体主页标签行共用，
/// token 同源（iosSecondaryFill / radiusNinetyNine / iosCaption2）。
class ObjectMetaChip extends StatelessWidget {
  const ObjectMetaChip({super.key, required this.label, this.accent = false});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final accentColor = AppColors.iosAccent(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: accent
            ? accentColor.withValues(alpha: 0.12)
            : AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: accent ? accentColor : AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}
