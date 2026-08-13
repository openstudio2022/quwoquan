import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_preparation_checkpoint.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource, ReferralSourceExt;
import 'package:quwoquan_app/runtime/platform/native_video_editing_bridge.dart';
import 'package:quwoquan_app/runtime/platform/startup_deferred_plugins.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/runtime/di/presentation/image_editor_page_factory.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_page_params.dart';
import 'package:quwoquan_app/runtime/di/presentation/content_media_creation_composition.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/desktop_picker_ports.dart';
import 'package:quwoquan_app/design_system/media/media_reorderable_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_page_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider;
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show circlesListQueryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show
        contentMediaSourceReaderProvider,
        contentMediaStreamObjectUploadProvider,
        createContentMediaFacetProvider,
        createContentMediaUploadServiceProvider,
        imageEditorFilterRepositoryProvider,
        mediaCaptureMetadataExtractorProvider,
        localVideoPlayabilityProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentFeatureFlagProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show createLocationCoordinatorProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show fileStorageGatewayProvider, platformCapabilitiesProvider;
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_typography_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/runtime/di/content_publication_epoch.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/create_editor_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/publish_capture_metadata_writer.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/article_entity_mention_picker.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_draft_session_controller.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_remote_helpers.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_provider_bridge.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/publish_circle_services.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/generated/content_publication_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_editor.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_publish_result_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_publish_confirm_sheet.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
part 'create_page_state.dart';
part 'create_page_state_helpers.dart';
part 'create_page_state_chrome_helpers.dart';
part 'create_page_state_draft_helpers.dart';
part 'create_page_state_media_helpers.dart';
part 'create_page_state_surface_helpers.dart';

final RouteObserver<ModalRoute<Object?>> createDraftRouteObserver =
    RouteObserver<ModalRoute<Object?>>();

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
    this.initialGatheringId,
    this.initialGatheringTitle,
    this.initialDraftId,
    this.mediaPickerPort,
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

  /// 从行动入口进入创作时的共同经历回流引用（可在创作页移除）。
  final String? initialGatheringId;
  final String? initialGatheringTitle;

  final String? initialDraftId;
  final MediaPickerPort? mediaPickerPort;
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
