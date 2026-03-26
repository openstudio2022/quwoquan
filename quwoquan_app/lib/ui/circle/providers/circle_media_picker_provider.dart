import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

enum CircleMediaPickSource { camera, photoLibrary }

abstract class CircleMediaPickerController {
  Future<String?> pickImage(
    BuildContext context, {
    required CircleMediaPickSource source,
  });
}

class DefaultCircleMediaPickerController
    implements CircleMediaPickerController {
  @override
  Future<String?> pickImage(
    BuildContext context, {
    required CircleMediaPickSource source,
  }) async {
    switch (source) {
      case CircleMediaPickSource.camera:
        final captured = await Navigator.of(context).push<CameraCaptureResult>(
          CupertinoPageRoute<CameraCaptureResult>(
            fullscreenDialog: true,
            builder: (_) => const CameraCapturePage(
              initialMode: MediaPickerEntryMode.image,
            ),
          ),
        );
        return captured?.type == CreateMediaType.image ? captured?.path : null;
      case CircleMediaPickSource.photoLibrary:
        final picked = await Navigator.of(context).push<CreateMediaPickerResult>(
          CupertinoPageRoute<CreateMediaPickerResult>(
            fullscreenDialog: true,
            builder: (_) => const CreateMediaPickerPage(
              entryMode: MediaPickerEntryMode.image,
              maxSelection: 1,
            ),
          ),
        );
        if (picked == null || picked.items.isEmpty) {
          return null;
        }
        final firstImage = picked.items.firstWhere(
          (item) => item.isImage,
          orElse: () => picked.items.first,
        );
        return firstImage.path;
    }
  }
}

final circleMediaPickerProvider = Provider<CircleMediaPickerController>((ref) {
  return DefaultCircleMediaPickerController();
});
