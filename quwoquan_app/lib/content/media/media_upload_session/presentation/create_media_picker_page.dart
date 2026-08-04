import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_page.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/create_media_picker_presentation.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/one_tap_movie_composer.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/one_tap_movie_preview_page.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/media_reorderable_view.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/media_creation_bottom_button.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/app_top_anchored_dropdown.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/app/navigation/generated/page_access_internal_routes.g.dart';
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
    this.initialSelection = const <CreateMediaItem>[],
    this.flowIntent = CreateMediaPickerFlowIntent.publish,
    MediaPickerService? mediaPickerService,
    OneTapMovieComposer? oneTapMovieComposer,
    this.imageEditorBuilder,
    this.cameraBuilder,
  }) : mediaPickerService = mediaPickerService ?? const MediaPickerService(),
       oneTapMovieComposer =
           oneTapMovieComposer ?? const MethodChannelOneTapMovieComposer();

  final MediaPickerEntryMode entryMode;
  final int maxSelection;
  final ImageEditorFilterRepository filterRepository;
  final List<CreateMediaItem> initialSelection;
  final CreateMediaPickerFlowIntent flowIntent;
  final MediaPickerService mediaPickerService;
  final OneTapMovieComposer oneTapMovieComposer;
  final CreateMediaPickerImageEditorBuilder? imageEditorBuilder;
  final CreateMediaPickerCameraBuilder? cameraBuilder;

  @override
  State<CreateMediaPickerPage> createState() => _CreateMediaPickerPageState();
}

@immutable
class _AlbumSortEntry {
  const _AlbumSortEntry({required this.album, required this.count});

  final AssetPathEntity album;
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
