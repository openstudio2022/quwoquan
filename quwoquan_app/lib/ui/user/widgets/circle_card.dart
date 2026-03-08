import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class CircleCard extends StatelessWidget {
  const CircleCard({
    super.key,
    required this.name,
    required this.coverUrl,
    required this.isDark,
    this.onTap,
  });

  final String name;
  final String coverUrl;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: border.withValues(alpha: 0.2)),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            AspectRatio(
              aspectRatio: 16 / 9,
              child: Image.network(
                coverUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => Container(
                  color: border.withValues(alpha: 0.1),
                  child: Icon(
                    Icons.group,
                    color: border,
                    size: AppSpacing.iconLarge,
                  ),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              child: Text(
                name,
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
