import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/features/create/models/create_media_models.dart';

class MediaPickerService {
  Future<bool> ensurePhotoPermission() async {
    final state = await PhotoManager.requestPermissionExtend();
    return state.isAuth || state.hasAccess;
  }

  Future<List<AssetPathEntity>> loadAlbums({
    required RequestType type,
  }) async {
    return PhotoManager.getAssetPathList(
      type: type,
      hasAll: true,
      filterOption: FilterOptionGroup(
        imageOption: const FilterOption(
          needTitle: true,
        ),
      ),
    );
  }

  Future<List<AssetEntity>> loadAssets({
    required AssetPathEntity album,
    required int page,
    required int pageSize,
  }) {
    return album.getAssetListPaged(page: page, size: pageSize);
  }

  Future<CreateMediaItem?> assetToMediaItem(
    AssetEntity entity, {
    CreateMediaSource source = CreateMediaSource.album,
  }) async {
    final file = await entity.file;
    final path = file?.path;
    if (path == null || path.isEmpty) return null;
    return CreateMediaItem(
      id: entity.id,
      path: path,
      type: _mediaTypeFromEntity(entity),
      source: source,
      width: entity.width,
      height: entity.height,
      durationMs: entity.duration * 1000,
      createdAtMs: entity.createDateTime.millisecondsSinceEpoch,
    );
  }

  CreateMediaItem fileToMediaItem({
    required String filePath,
    required CreateMediaSource source,
    required CreateMediaType type,
  }) {
    return CreateMediaItem(
      id: '${source.name}-${DateTime.now().microsecondsSinceEpoch}',
      path: filePath,
      type: type,
      source: source,
      width: 0,
      height: 0,
      durationMs: 0,
      createdAtMs: DateTime.now().millisecondsSinceEpoch,
    );
  }

  CreateMediaType _mediaTypeFromEntity(AssetEntity entity) {
    if (entity.type == AssetType.video) {
      return CreateMediaType.video;
    }
    final mime = (entity.mimeType ?? '').toLowerCase();
    if (mime.contains('gif')) {
      return CreateMediaType.gif;
    }
    return CreateMediaType.image;
  }
}
