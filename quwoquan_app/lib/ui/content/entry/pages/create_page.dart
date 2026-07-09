import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:video_thumbnail/video_thumbnail.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/cloud/runtime/startup_deferred_plugins.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/camera/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_image_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/desktop/desktop_picker_services.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/constants/create_page_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/media/local_video_file_readiness.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_typography_page.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/video_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_draft_store_provider.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/entry/services/article_entity_mention_picker.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_session_controller.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_publish_confirm_sheet.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
part 'create_page_state.dart';
part 'create_page_state_helpers.dart';
part 'create_page_state_media_helpers.dart';

final RouteObserver<ModalRoute<dynamic>> createDraftRouteObserver =
    RouteObserver<ModalRoute<dynamic>>();

typedef CreateMediaPickerLauncher =
    Future<CreateMediaPickerResult?> Function(
      BuildContext context, {
      required MediaPickerEntryMode mode,
      required int maxSelection,
      List<String> initialPaths,
    });

typedef CreateCameraPageBuilder =
    Widget Function(
      BuildContext context, {
      required MediaPickerEntryMode initialMode,
      required CameraPhotoCaller caller,
      required CameraPhotoEntrySource entrySource,
      required int selectedCountBeforeCapture,
    });

class CreateVideoPreparationResult {
  const CreateVideoPreparationResult({
    required this.durationMs,
    this.thumbnailPath = '',
    this.width = 0,
    this.height = 0,
  });

  final int durationMs;
  final String thumbnailPath;
  final int width;
  final int height;
}

typedef CreateVideoPreparationProbe =
    Future<CreateVideoPreparationResult> Function(String path);

typedef CreateVideoEditorLauncher =
    Future<VideoEditorResult?> Function(
      BuildContext context, {
      required CreateEditorState state,
    });

class CreatePage extends ConsumerStatefulWidget {
  const CreatePage({
    super.key,
    this.initialAction,
    this.initialTabKey,
    this.initialHomepage,
    this.initialCircleId,
    this.initialCircleName,
    this.initialDraftId,
    this.mediaPickerLauncher,
    this.cameraPageBuilder,
    this.videoPreparationProbe,
    this.videoEditorLauncher,
  });

  final EditorStartAction? initialAction;
  final String? initialTabKey;
  final HomepageCanonicalReference? initialHomepage;

  final String? initialCircleId;
  final String? initialCircleName;

  final String? initialDraftId;
  final CreateMediaPickerLauncher? mediaPickerLauncher;
  final CreateCameraPageBuilder? cameraPageBuilder;
  final CreateVideoPreparationProbe? videoPreparationProbe;
  final CreateVideoEditorLauncher? videoEditorLauncher;

  @override
  ConsumerState<CreatePage> createState() => _CreatePageState();
}

class _PreviewBadge extends StatelessWidget {
  const _PreviewBadge({required this.label, this.backgroundColor});

  final String label;
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bg =
        backgroundColor ??
        mediaScrimBackdrop(isDark).withValues(alpha: isDark ? 0.42 : 0.45);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.badgeForeground);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }

  static Color mediaScrimBackdrop(bool isDark) =>
      AppColorsFunctional.getColor(isDark, ColorType.createMediaOverlayBase);
}

class _VideoMetadataProbe {
  const _VideoMetadataProbe({
    required this.durationMs,
    required this.width,
    required this.height,
  });

  static const _VideoMetadataProbe empty = _VideoMetadataProbe(
    durationMs: 0,
    width: _emptyMediaExtent,
    height: _emptyMediaExtent,
  );
  static const int _emptyMediaExtent = 0;

  final int durationMs;
  final int width;
  final int height;
}

class _VideoEditContext {
  const _VideoEditContext({
    required this.trimStartMs,
    required this.trimEndMs,
    required this.coverTimeMs,
    required this.muted,
  });

  final int trimStartMs;
  final int trimEndMs;
  final int coverTimeMs;
  final bool muted;
}

class _AddThumbnailButton extends StatelessWidget {
  const _AddThumbnailButton({
    super.key,
    required this.onPressed,
    required this.width,
    required this.height,
    required this.label,
    this.enabled = true,
  });

  final Future<void> Function() onPressed;
  final double width;
  final double height;
  final String label;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final accent = enabled
        ? AppColors.iosAccentLight
        : CupertinoColors.tertiaryLabel.resolveFrom(context);
    return GestureDetector(
      onTap: enabled ? () => onPressed() : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        width: width,
        height: height,
        padding: EdgeInsets.all(AppSpacing.containerSm),
        decoration: BoxDecoration(
          color: enabled
              ? CupertinoColors.systemBackground.resolveFrom(context)
              : CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
                  context,
                ),
          borderRadius: BorderRadius.circular(AppSpacing.containerSm),
          border: Border.all(
            color: enabled
                ? AppColors.iosAccentLight.withValues(alpha: 0.24)
                : CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.18),
            width: AppSpacing.hairline,
          ),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: enabled
                  ? AppColors.iosAccentLight.withValues(alpha: 0.06)
                  : AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundPrimary,
                    ).withValues(alpha: 0.045),
              blurRadius: AppSpacing.ten,
              offset: const Offset(0, AppSpacing.contentSpacingXs),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(CupertinoIcons.add, color: accent, size: AppSpacing.iconLarge),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: accent,
                fontSize: AppTypography.smPlus,
                fontWeight: AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
