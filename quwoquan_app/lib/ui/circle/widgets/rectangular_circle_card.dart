import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

class RectangularCircleCard extends StatelessWidget {
  final CircleDto circle;
  final VoidCallback? onTap;
  final double width;
  final double aspectRatio;

  const RectangularCircleCard({
    super.key,
    required this.circle,
    this.onTap,
    this.width = 280,
    this.aspectRatio = 16 / 9,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.08),
              blurRadius: 8,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            // Cover Image
            Positioned.fill(
              child: AppCachedNetworkImage(
                imageUrl: circle.coverUrl ?? circle.coverUrl ?? '',
                fit: BoxFit.cover,
              ),
            ),

            // Gradient Overlay
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.transparent,
                      Colors.black.withValues(alpha: 0.2),
                      Colors.black.withValues(alpha: 0.8),
                    ],
                    stops: const [0.4, 0.7, 1.0],
                  ),
                ),
              ),
            ),

            // Content
            Positioned(
              left: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              bottom: AppSpacing.containerMd,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Tags / Category Pill
                  if (circle.subCategory != null)
                    Container(
                      margin: const EdgeInsets.only(bottom: 4),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius,
                        ),
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.1),
                          width: AppSpacing.hairline,
                        ),
                      ),
                      child: Text(
                        circle.subCategory!,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: AppTypography.xs,
                          fontWeight: AppTypography.medium,
                        ),
                      ),
                    ),

                  // Circle Name
                  Text(
                    circle.name,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.bold,
                      height: AppTypography.lineHeightTight,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),

                  const SizedBox(height: AppSpacing.xs),

                  // Stats & Desc
                  Row(
                    children: [
                      // Member Count
                      Icon(
                        Icons.people_rounded,
                        size: AppTypography.sm,
                        color: Colors.white.withValues(alpha: 0.8),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Text(
                        _formatNumber(circle.memberCount),
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.8),
                          fontSize: AppTypography.xsPlus,
                        ),
                      ),
                      const SizedBox(width: AppSpacing.sm),

                      // Description (truncated)
                      Expanded(
                        child: Text(
                          circle.description ?? '',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.7),
                            fontSize: AppTypography.xsPlus,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Optional: Join/Enter Icon Button
            Positioned(
              right: 8,
              bottom: 8,
              child: Container(
                padding: const EdgeInsets.all(AppSpacing.six),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.arrow_forward_ios_rounded,
                  color: Colors.white,
                  size: AppTypography.sm,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatNumber(int count) {
    if (count >= 10000) {
      return '${(count / 10000).toStringAsFixed(1)}w';
    }
    if (count >= 1000) {
      return '${(count / 1000).toStringAsFixed(1)}k';
    }
    return count.toString();
  }
}
