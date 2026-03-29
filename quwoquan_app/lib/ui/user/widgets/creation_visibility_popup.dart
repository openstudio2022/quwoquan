import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

class CreationVisibilityPopup extends StatelessWidget {
  const CreationVisibilityPopup({
    super.key,
    required this.mode,
    required this.current,
    required this.isDark,
    required this.onSelected,
  });

  final ProfileMode mode;
  final CreationVisibility current;
  final bool isDark;
  final ValueChanged<CreationVisibility> onSelected;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    final primary = AppColors.primaryColor;

    final options = mode == ProfileMode.mine
        ? CreationVisibility.values
        : [CreationVisibility.all, CreationVisibility.public_];

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.12),
            blurRadius: AppSpacing.sm,
            offset: Offset(0, AppSpacing.intraGroupXs),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: options.map((v) {
          final isActive = v == current;
          return GestureDetector(
            onTap: () => onSelected(v),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupMd,
              ),
              decoration: isActive
                  ? BoxDecoration(
                      color: primary.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                    )
                  : null,
              child: Text(
                _label(v),
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: isActive ? AppTypography.semiBold : AppTypography.normal,
                  color: isActive ? primary : fg,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  String _label(CreationVisibility v) {
    switch (v) {
      case CreationVisibility.all:
        return '全部';
      case CreationVisibility.public_:
        return '公开';
      case CreationVisibility.private_:
        return '私密';
    }
  }
}
