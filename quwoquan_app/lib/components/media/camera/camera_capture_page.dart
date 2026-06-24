import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_shell.dart';
import 'package:quwoquan_app/components/media/camera/camera_filter_strip.dart';
import 'package:quwoquan_app/components/media/camera/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_matrix.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/core/media/local_video_file_readiness.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
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

@immutable
class CameraCaptureResult {
  const CameraCaptureResult({
    required this.path,
    required this.type,
    this.filterPresetId = 'original',
    this.entrySource = CameraPhotoEntrySource.photoPicker,
  });

  final String path;
  final CreateMediaType type;
  final String filterPresetId;
  final CameraPhotoEntrySource entrySource;
}

enum _MicrophoneDecision { audio, muted, abort }

enum _MicrophoneChoice { openSettings, continueMuted }

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({
    super.key,
    required this.initialMode,
    this.allowVideoMode = true,
    this.initialCapturedPhotoPath,
    this.caller = CameraPhotoCaller.picker,
    this.entrySource = CameraPhotoEntrySource.photoPicker,
    this.selectedCountBeforeCapture = 0,
    this.filterRepository,
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
    this.minRecordingMs = 1000,
    this.maxRecordingMs = 60000,
  });

  final MediaPickerEntryMode initialMode;
  final bool allowVideoMode;
  final String? initialCapturedPhotoPath;
  final CameraPhotoCaller caller;
  final CameraPhotoEntrySource entrySource;
  final int selectedCountBeforeCapture;
  final ImageEditorFilterRepository? filterRepository;
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
