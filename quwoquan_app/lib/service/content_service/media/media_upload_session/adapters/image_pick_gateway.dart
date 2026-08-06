import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/image_pick_source.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';

/// 领域无关的单张图片选择能力：相机拍摄或相册选择后返回本地文件路径。
///
/// profile 资料编辑、circle 圈子编辑等「换头像 / 换封面」统一复用，
/// 避免各域复制 picker 并产生不同选择语义。
/// `cameraRouteName` / `galleryRouteName` 由调用方传入，用于 page-access 追踪
/// 区分来源（与 [page_access_internal_routes] 常量保持一致）。
abstract class ImagePickGateway {
  Future<String?> pickImage(
    BuildContext context, {
    required ImagePickSource source,
    required String cameraRouteName,
    required String galleryRouteName,
  });
}

class DefaultImagePickGateway implements ImagePickGateway {
  const DefaultImagePickGateway(this._filterRepository, this._mediaPickerPort);

  final ImageEditorFilterCatalog _filterRepository;
  final MediaPickerPort _mediaPickerPort;

  @override
  Future<String?> pickImage(
    BuildContext context, {
    required ImagePickSource source,
    required String cameraRouteName,
    required String galleryRouteName,
  }) async {
    switch (source) {
      case ImagePickSource.camera:
        final captured = await Navigator.of(context).push<CameraCaptureResult>(
          CupertinoPageRoute<CameraCaptureResult>(
            settings: RouteSettings(name: cameraRouteName),
            fullscreenDialog: true,
            builder: (_) => CameraCapturePage(
              initialMode: MediaPickerEntryMode.image,
              filterRepository: _filterRepository,
            ),
          ),
        );
        return captured?.type == CreateMediaType.image ? captured?.path : null;
      case ImagePickSource.photoLibrary:
        final picked = await Navigator.of(context)
            .push<CreateMediaPickerResult>(
              CupertinoPageRoute<CreateMediaPickerResult>(
                settings: RouteSettings(name: galleryRouteName),
                fullscreenDialog: true,
                builder: (_) => CreateMediaPickerPage(
                  entryMode: MediaPickerEntryMode.image,
                  maxSelection: 1,
                  filterRepository: _filterRepository,
                  mediaPickerPort: _mediaPickerPort,
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
