import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 单张图片选择来源（相机 / 相册），领域无关。
enum ImagePickSource { camera, photoLibrary }

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
  const DefaultImagePickGateway(this._filterRepository);

  final ImageEditorFilterRepository _filterRepository;

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

final imagePickGatewayProvider = Provider<ImagePickGateway>((ref) {
  return DefaultImagePickGateway(
    ref.watch(imageEditorFilterRepositoryProvider),
  );
});
