import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show Circle;
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

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

class MyCirclesRail extends ConsumerWidget {
  final List<Circle> circles;
  final ValueChanged<Circle> onCircleTap;

  const MyCirclesRail({
    super.key,
    required this.circles,
    required this.onCircleTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (circles.isEmpty) return const SizedBox.shrink();
    final isDark = ref.watch(isDarkProvider);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final surfaceMuted = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );

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
            return _buildMoreButton(fgSecondary, surfaceMuted);
          }
          return _buildCircleItem(circles[index], fgSecondary);
        },
      ),
    );
  }

  Widget _buildCircleItem(Circle circle, Color fgSecondary) {
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
                color: fgSecondary.withValues(alpha: 0.2),
                width: AppSpacing.one,
              ),
            ),
            child: ClipOval(
              child: AppMediaImage(
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
              style: _myCirclesRailLabelStyle().copyWith(color: fgSecondary),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMoreButton(Color fgSecondary, Color surfaceMuted) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: AppSpacing.avatarCircleLg,
          height: AppSpacing.avatarCircleLg,
          decoration: BoxDecoration(
            color: surfaceMuted,
            shape: BoxShape.circle,
          ),
          child: Icon(
            Icons.grid_view_rounded, // Or "All" icon
            color: fgSecondary,
            size: AppSpacing.iconMedium,
          ),
        ),
        const SizedBox(height: AppSpacing.intraGroupXs),
        SizedBox(
          width: AppSpacing.largeAvatarSize,
          child: Text(
            CommunityText.circleAll,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: _myCirclesRailLabelStyle().copyWith(color: fgSecondary),
          ),
        ),
      ],
    );
  }
}
