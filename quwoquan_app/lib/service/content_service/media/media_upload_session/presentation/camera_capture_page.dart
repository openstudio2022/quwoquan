import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_shell.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_filter_strip.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_session_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/design_system/media/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_matrix.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/runtime/di/presentation/image_editor_page_factory.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/local_video_file_readiness.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/local_video_playability.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_action_feedback.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:video_player/video_player.dart';
part 'camera_capture_page_state.dart';
part 'camera_capture_page_state_helpers.dart';

typedef CameraPhotoTelemetry =
    FutureOr<void> Function(String eventName, Map<String, String> parameters);

typedef CameraPhotoEditorLauncher =
    Future<String?> Function(
      BuildContext context,
      CameraPhotoEditorRequest request,
    );

typedef CameraPhotoCapture = Future<String> Function();

typedef CameraPreviewBuilder = Widget Function(BuildContext context);

/// 视频录制注入点：测试可用 fake 录制器跑通状态机，无需真实相机。
typedef CameraVideoRecordingStart = Future<void> Function();
typedef CameraVideoRecordingStop = Future<String> Function();

/// 麦克风权限注入点：返回是否已授权。
typedef CameraMicrophonePermissionRequest = Future<bool> Function();

/// 录后预览注入点：测试用占位预览替代真实 `video_player`。
typedef CameraVideoPreviewBuilder =
    Widget Function(BuildContext context, String videoPath);

@immutable
class CameraPhotoEditorRequest {
  const CameraPhotoEditorRequest({
    required this.path,
    required this.filterPresetId,
    required this.filterStrength,
    required this.caller,
    required this.entrySource,
  });

  final String path;
  final String filterPresetId;
  final double filterStrength;
  final CameraPhotoCaller caller;
  final CameraPhotoEntrySource entrySource;
}

enum _MicrophoneDecision { audio, muted, abort }

enum _MicrophoneChoice { openSettings, continueMuted }

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({
    super.key,
    required this.initialMode,
    this.allowVideoMode = true,
    this.modePolicy,
    this.initialCapturedPhotoPath,
    this.caller = CameraPhotoCaller.picker,
    this.entrySource = CameraPhotoEntrySource.photoPicker,
    this.selectedCountBeforeCapture = 0,
    required this.filterRepository,
    this.imageEditorLauncher,
    this.photoCapture,
    this.previewBuilder,
    this.previewCameraDescriptions = const <CameraDescription>[],
    this.telemetry,
    this.cameraDiscovery = availableCameras,
    this.videoRecordingStart,
    this.videoRecordingStop,
    this.microphonePermissionRequest,
    this.videoPreviewBuilder,
    this.videoFileReadyProbe,
    this.fileStorageGateway,
    this.minRecordingMs = 1000,
    this.maxRecordingMs = 60000,
  });

  final MediaPickerEntryMode initialMode;
  final bool allowVideoMode;
  final CameraCaptureModePolicy? modePolicy;
  final String? initialCapturedPhotoPath;
  final CameraPhotoCaller caller;
  final CameraPhotoEntrySource entrySource;
  final int selectedCountBeforeCapture;
  final ImageEditorFilterCatalog filterRepository;
  final CameraPhotoEditorLauncher? imageEditorLauncher;
  final CameraPhotoCapture? photoCapture;
  final CameraPreviewBuilder? previewBuilder;
  final List<CameraDescription> previewCameraDescriptions;
  final CameraPhotoTelemetry? telemetry;
  final Future<List<CameraDescription>> Function() cameraDiscovery;
  final CameraVideoRecordingStart? videoRecordingStart;
  final CameraVideoRecordingStop? videoRecordingStop;
  final CameraMicrophonePermissionRequest? microphonePermissionRequest;
  final CameraVideoPreviewBuilder? videoPreviewBuilder;
  final LocalVideoFileReadyProbe? videoFileReadyProbe;
  final FileStorageGateway? fileStorageGateway;
  final int minRecordingMs;
  final int maxRecordingMs;

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

/// 录后预览：自动循环播放本地录制视频，加载失败时回落深色占位。
class _RecordedVideoPreview extends StatefulWidget {
  const _RecordedVideoPreview({
    super.key,
    required this.path,
    required this.readyProbe,
    required this.onReady,
    required this.onFailed,
  });

  final String path;
  final LocalVideoFileReadyProbe readyProbe;
  final VoidCallback onReady;
  final VoidCallback onFailed;

  @override
  State<_RecordedVideoPreview> createState() => _RecordedVideoPreviewState();
}
