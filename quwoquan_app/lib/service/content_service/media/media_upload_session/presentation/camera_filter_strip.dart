import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

class CameraFilterStrip extends StatelessWidget {
  const CameraFilterStrip({
    super.key,
    required this.presets,
    required this.selectedPresetId,
    required this.onSelected,
  });

  static const double thumbnailSize = 56;

  final List<ImageEditorFilterPreset> presets;
  final String selectedPresetId;
  final ValueChanged<ImageEditorFilterPreset> onSelected;

  @override
  Widget build(BuildContext context) {
    if (presets.isEmpty) {
      return const SizedBox.shrink();
    }
    return SizedBox(
      key: const ValueKey<String>('camera-filter-strip'),
      height: thumbnailSize + AppSpacing.buttonHeightSm,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        itemCount: presets.length,
        separatorBuilder: (context, index) =>
            SizedBox(width: AppSpacing.intraGroupSm),
        itemBuilder: (context, index) {
          final preset = presets[index];
          return _CameraFilterTile(
            preset: preset,
            selected: preset.id == selectedPresetId,
            onTap: () => onSelected(preset),
          );
        },
      ),
    );
  }
}

class _CameraFilterTile extends StatelessWidget {
  const _CameraFilterTile({
    required this.preset,
    required this.selected,
    required this.onTap,
  });

  final ImageEditorFilterPreset preset;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final borderColor = selected
        ? AppColors.primaryColor
        : AppColors.white.withValues(alpha: 0.18);
    return CupertinoButton(
      key: ValueKey<String>('camera-filter-${preset.id}'),
      minimumSize: Size.zero,
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: SizedBox(
        width: CameraFilterStrip.thumbnailSize,
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: CameraFilterStrip.thumbnailSize,
                height: CameraFilterStrip.thumbnailSize,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  gradient: _previewGradient(preset.id),
                  border: Border.all(
                    color: borderColor,
                    width: selected
                        ? AppSpacing.hairline * 3
                        : AppSpacing.hairline,
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              SizedBox(
                width: CameraFilterStrip.thumbnailSize,
                child: Text(
                  preset.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: selected
                        ? AppColors.primaryColor
                        : AppColors.white.withValues(alpha: 0.70),
                    fontSize: AppTypography.iosCaption1,
                    fontWeight: selected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  LinearGradient _previewGradient(String presetId) {
    switch (presetId) {
      case 'warm':
        return const LinearGradient(
          colors: [
            AppColors.iosGroupedSurfaceDark,
            AppColors.imageEditorHslOrange,
          ],
        );
      case 'cool':
        return const LinearGradient(
          colors: [
            AppColors.iosGroupedSurfaceDark,
            AppColors.iosSystemCyanAccent,
          ],
        );
      case 'dramatic':
        return const LinearGradient(
          colors: [AppColors.black, AppColors.iosToolbarSecondaryIconDark],
        );
      case 'mono':
        return const LinearGradient(colors: [AppColors.black, AppColors.white]);
      case 'vivid':
        return const LinearGradient(
          colors: [
            AppColors.imageEditorHslGreen,
            AppColors.imageEditorHslYellow,
          ],
        );
      case 'original':
      default:
        return const LinearGradient(
          colors: [
            AppColors.iosGroupedSurfaceDark,
            AppColors.iosGroupedSurfaceElevatedDark,
          ],
        );
    }
  }
}
