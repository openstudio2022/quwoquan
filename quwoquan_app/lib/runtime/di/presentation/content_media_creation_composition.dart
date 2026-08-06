import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/desktop_image_picker_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/video_editor_page.dart';

/// Concrete media-creation page composition shared by Content Post and the
/// Media Upload Session object. Object presentation code depends only on the
/// public launch values and delegates concrete widget construction here.
abstract final class ContentMediaCreationComposition {
  static Widget desktopPicker({required int maxSelection}) {
    return DesktopImagePickerPage(maxSelection: maxSelection);
  }

  static Widget mediaPicker({
    required MediaPickerEntryMode mode,
    required int maxSelection,
    required List<CreateMediaItem> initialSelection,
    required ImageEditorFilterCatalog filterRepository,
    required MediaPickerPort mediaPickerPort,
  }) {
    return CreateMediaPickerPage(
      entryMode: mode,
      maxSelection: maxSelection,
      initialSelection: initialSelection,
      filterRepository: filterRepository,
      mediaPickerPort: mediaPickerPort,
    );
  }

  static Widget camera({
    required MediaPickerEntryMode initialMode,
    required CameraCaptureModePolicy modePolicy,
    required CameraPhotoCaller caller,
    required CameraPhotoEntrySource entrySource,
    required int selectedCountBeforeCapture,
    required ImageEditorFilterCatalog filterRepository,
  }) {
    return CameraCapturePage(
      initialMode: initialMode,
      modePolicy: modePolicy,
      caller: caller,
      entrySource: entrySource,
      selectedCountBeforeCapture: selectedCountBeforeCapture,
      filterRepository: filterRepository,
    );
  }

  static Widget videoEditor({
    required String sourceVideoPath,
    required String initialVideoPath,
    required String initialThumbnailPath,
    required int initialDurationMs,
    required int initialTrimStartMs,
    required int initialTrimEndMs,
    required int initialCoverTimeMs,
    required bool initialMuted,
  }) {
    return VideoEditorPage(
      sourceVideoPath: sourceVideoPath,
      initialVideoPath: initialVideoPath,
      initialThumbnailPath: initialThumbnailPath,
      initialDurationMs: initialDurationMs,
      initialTrimStartMs: initialTrimStartMs,
      initialTrimEndMs: initialTrimEndMs,
      initialCoverTimeMs: initialCoverTimeMs,
      initialMuted: initialMuted,
    );
  }
}
