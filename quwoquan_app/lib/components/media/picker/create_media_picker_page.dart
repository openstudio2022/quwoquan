import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/camera/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/app_top_anchored_dropdown.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
part 'create_media_picker_page_state.dart';
part 'create_media_picker_page_state_helpers.dart';

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
    this.initialSelection = const <CreateMediaItem>[],
    MediaPickerService? mediaPickerService,
    this.imageEditorBuilder,
    this.cameraBuilder,
  }) : mediaPickerService = mediaPickerService ?? const MediaPickerService();

  final MediaPickerEntryMode entryMode;
  final int maxSelection;
  final List<CreateMediaItem> initialSelection;
  final MediaPickerService mediaPickerService;
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
class _EditedPickerImage {
  const _EditedPickerImage({required this.selectedIndex, required this.path});

  final int selectedIndex;
  final String path;
}
