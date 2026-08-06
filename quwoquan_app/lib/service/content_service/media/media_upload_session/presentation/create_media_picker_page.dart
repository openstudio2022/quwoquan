import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/runtime/di/presentation/image_editor_page_factory.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_presentation.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/one_tap_movie_composer.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/one_tap_movie_preview_page.dart';
import 'package:quwoquan_app/design_system/media/media_reorderable_view.dart';
import 'package:quwoquan_app/design_system/media/media_creation_bottom_button.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_top_anchored_dropdown.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
part 'create_media_picker_page_state.dart';
part 'create_media_picker_page_state_helpers.dart';
part 'create_media_picker_page_chrome.dart';

typedef CreateMediaPickerImageEditorBuilder =
    Widget Function(
      BuildContext context,
      CreateMediaPickerImageEditorRequest request,
    );

typedef CreateMediaPickerCameraBuilder =
    Widget Function(
      BuildContext context,
      CameraPhotoCaller caller,
      CameraPhotoEntrySource entrySource,
      int selectedCountBeforeCapture,
    );

@immutable
class CreateMediaPickerImageEditorRequest {
  const CreateMediaPickerImageEditorRequest({
    required this.initialPath,
    required this.index,
    required this.total,
    required this.imagePaths,
  });

  final String initialPath;
  final int index;
  final int total;
  final List<String> imagePaths;
}

class CreateMediaPickerPage extends StatefulWidget {
  const CreateMediaPickerPage({
    super.key,
    required this.entryMode,
    required this.maxSelection,
    required this.filterRepository,
    required this.mediaPickerPort,
    this.initialSelection = const <CreateMediaItem>[],
    this.flowIntent = CreateMediaPickerFlowIntent.publish,
    OneTapMovieComposer? oneTapMovieComposer,
    this.imageEditorBuilder,
    this.cameraBuilder,
  }) : oneTapMovieComposer =
           oneTapMovieComposer ?? const MethodChannelOneTapMovieComposer();

  final MediaPickerEntryMode entryMode;
  final int maxSelection;
  final ImageEditorFilterCatalog filterRepository;
  final List<CreateMediaItem> initialSelection;
  final CreateMediaPickerFlowIntent flowIntent;
  final MediaPickerPort mediaPickerPort;
  final OneTapMovieComposer oneTapMovieComposer;
  final CreateMediaPickerImageEditorBuilder? imageEditorBuilder;
  final CreateMediaPickerCameraBuilder? cameraBuilder;

  @override
  State<CreateMediaPickerPage> createState() => _CreateMediaPickerPageState();
}

@immutable
class _AlbumSortEntry {
  const _AlbumSortEntry({required this.album, required this.count});

  final MediaPickerAlbumRef album;
  final int count;
}

@immutable
class _EditedPickerImages {
  const _EditedPickerImages({
    required this.items,
    required this.currentImageIndex,
    required this.continueToCreate,
  });

  final List<CreateMediaItem> items;
  final int currentImageIndex;
  final bool continueToCreate;
}
