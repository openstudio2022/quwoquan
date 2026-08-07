import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/local_video_file_readiness.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/local_video_playability.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/runtime/platform/ios_video_editing_bridge.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart'
    show runtimeErrorSemantic;
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/design_system/media/media_creation_bottom_button.dart';
import 'package:video_player/video_player.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
part 'video_editor_page_state.dart';
part 'video_editor_page_state_cover.dart';

/// 本地视频剪辑；持久草稿在父链 `CreateEditorState`（`ContentPublishDraftComposite`）。
/// 剪辑结果回写草稿后，发布确认页的帖子元数据预览与 `publish_draft_projection_bridge`
///（`postReadPreviewFromPublishConfirmSummary`）同源。
class VideoEditorPage extends ConsumerStatefulWidget {
  const VideoEditorPage({
    super.key,
    required this.sourceVideoPath,
    required this.initialVideoPath,
    required this.initialThumbnailPath,
    required this.initialDurationMs,
    required this.initialTrimStartMs,
    required this.initialTrimEndMs,
    required this.initialCoverTimeMs,
    required this.initialMuted,
    this.editingService,
    this.videoFileReadyProbe,
  });

  final String sourceVideoPath;
  final String initialVideoPath;
  final String initialThumbnailPath;
  final int initialDurationMs;
  final int initialTrimStartMs;
  final int initialTrimEndMs;
  final int initialCoverTimeMs;
  final bool initialMuted;
  final IosVideoEditingService? editingService;
  final LocalVideoFileReadyProbe? videoFileReadyProbe;

  @override
  ConsumerState<VideoEditorPage> createState() => _VideoEditorPageState();
}

class _EditorSection extends StatelessWidget {
  const _EditorSection({
    required this.title,
    required this.child,
    this.trailing,
  });

  final String title;
  final String? trailing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
          context,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                title,
                style: const TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              const Spacer(),
              if (trailing != null)
                Text(
                  trailing!,
                  style: TextStyle(
                    color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    fontSize: AppTypography.sm,
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          child,
        ],
      ),
    );
  }
}

class _EditorToggleChip extends StatelessWidget {
  const _EditorToggleChip({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    final selectedBackground = AppColors.primaryColor.withValues(alpha: 0.14);
    final idleBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    ).withValues(alpha: 0.72);
    final selectedBorder = AppColors.primaryColor.withValues(alpha: 0.78);
    final idleBorder = AppColors.white.withValues(alpha: 0.10);
    final foreground = selected
        ? AppColors.primaryColor
        : AppColors.white.withValues(alpha: 0.90);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: Container(
        height: AppSpacing.buttonHeightLg + AppSpacing.containerLg,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerXs,
          vertical: AppSpacing.containerSm,
        ),
        decoration: BoxDecoration(
          color: selected ? selectedBackground : idleBackground,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: selected ? selectedBorder : idleBorder),
          boxShadow: [
            BoxShadow(
              color: AppColors.black.withValues(alpha: 0.18),
              blurRadius: AppSpacing.containerSm,
              offset: Offset(0, AppSpacing.two),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(icon, size: AppSpacing.iconLarge, color: foreground),
            SizedBox(height: AppSpacing.intraGroupSm),
            Flexible(
              child: Text(
                label,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: foreground,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
