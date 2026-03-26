import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';

TextStyle _myCirclesRailLabelStyle() {
  return const TextStyle(fontSize: AppTypography.xsPlus);
}

double _myCirclesRailHeight(BuildContext context) {
  final painter = TextPainter(
    text: TextSpan(text: 'Hg', style: _myCirclesRailLabelStyle()),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 1,
  )..layout();
  final adaptiveHeight =
      AppSpacing.avatarCircleLg + AppSpacing.intraGroupXs + painter.height;
  return adaptiveHeight > AppSpacing.avatarRailHeight
      ? adaptiveHeight
      : AppSpacing.avatarRailHeight;
}

class MyCirclesRail extends StatelessWidget {
  final List<CircleDto> circles;
  final Function(CircleDto) onCircleTap;

  const MyCirclesRail({
    super.key,
    required this.circles,
    required this.onCircleTap,
  });

  @override
  Widget build(BuildContext context) {
    if (circles.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      height: _myCirclesRailHeight(context),
      child: ListView.separated(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        scrollDirection: Axis.horizontal,
        itemCount: circles.length + 1, // +1 for "More" or "Create"
        separatorBuilder: (context, index) =>
            const SizedBox(width: AppSpacing.intraGroupMd),
        itemBuilder: (context, index) {
          if (index == circles.length) {
            return _buildMoreButton(context);
          }
          return _buildCircleItem(circles[index]);
        },
      ),
    );
  }

  Widget _buildCircleItem(CircleDto circle) {
    return GestureDetector(
      onTap: () => onCircleTap(circle),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: AppSpacing.avatarCircleLg,
            height: AppSpacing.avatarCircleLg,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: AppColors.light.foregroundSecondary.withValues(
                  alpha: 0.2,
                ),
                width: AppSpacing.one,
              ),
            ),
            child: ClipOval(
              child: CircleMediaImage(
                imageSource: circle.coverUrl ?? '',
                fit: BoxFit.cover,
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            width: AppSpacing.largeAvatarSize,
            child: Text(
              circle.name,
              style: _myCirclesRailLabelStyle().copyWith(
                color: AppColors.light.foregroundSecondary,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMoreButton(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: AppSpacing.avatarCircleLg,
          height: AppSpacing.avatarCircleLg,
          decoration: BoxDecoration(
            color: AppColors.light.backgroundSecondary,
            shape: BoxShape.circle,
          ),
          child: Icon(
            Icons.grid_view_rounded, // Or "All" icon
            color: AppColors.light.foregroundSecondary,
            size: AppSpacing.iconMedium,
          ),
        ),
        const SizedBox(height: AppSpacing.intraGroupXs),
        SizedBox(
          width: AppSpacing.largeAvatarSize,
          child: Text(
            '全部',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: _myCirclesRailLabelStyle().copyWith(
              color: AppColors.light.foregroundSecondary,
            ),
          ),
        ),
      ],
    );
  }
}
