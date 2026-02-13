import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';

/// 底栏/工具列表通用入口（图标 + 文案）
class ImageEditorToolEntryChip extends StatelessWidget {
  const ImageEditorToolEntryChip({
    super.key,
    this.icon,
    this.semanticIconKey,
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  final IconData? icon;
  final String? semanticIconKey;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final color = isSelected ? fg : fgSecondary.withValues(alpha: 0.82);
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          minWidth: AppSpacing.minInteractiveSize,
          minHeight: AppSpacing.minInteractiveSize,
        ),
        child: FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.center,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (semanticIconKey != null)
                ImageEditorSemanticIcon(
                  iconKey: semanticIconKey!,
                  size: AppSpacing.iconLarge,
                  color: color,
                )
              else
                Icon(
                  icon,
                  size: AppSpacing.iconLarge,
                  color: color,
                ),
              SizedBox(height: AppSpacing.toolPanelItemIconLabelGap),
              Text(
                label,
                style: TextStyle(
                  fontSize: AppTypography.toolPanelItemLabel,
                  color: color,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
