import 'dart:typed_data';

import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

class MediaPickerService {
  const MediaPickerService();

  // photo_manager 解码/分页参数，非视觉 dp：相册封面只需取首张资产，缩略图按解码分辨率请求。
  static const int _coverProbePageSize = 1;
  static const int _coverThumbnailPixelSize = 160;
  static const int _defaultThumbnailPixelSize = 240;

  Future<bool> ensurePhotoPermission() async {
    final state = await PhotoManager.requestPermissionExtend();
    return state.isAuth || state.hasAccess;
  }

  Future<List<AssetPathEntity>> loadAlbums({required RequestType type}) async {
    return PhotoManager.getAssetPathList(
      type: type,
      hasAll: true,
      filterOption: FilterOptionGroup(
        imageOption: const FilterOption(needTitle: true),
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

  Future<int> loadAlbumAssetCount(AssetPathEntity album) {
    return album.assetCountAsync;
  }

  Future<Uint8List?> loadAlbumCover(AssetPathEntity album) async {
    final assets = await album.getAssetListPaged(
      page: 0,
      size: _coverProbePageSize,
    );
    if (assets.isEmpty) {
      return null;
    }
    return loadThumbnail(assets.first, size: _coverThumbnailPixelSize);
  }

  Future<Uint8List?> loadThumbnail(
    AssetEntity entity, {
    int size = _defaultThumbnailPixelSize,
  }) {
    return entity.thumbnailDataWithSize(ThumbnailSize.square(size));
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
      width:
          0, // ignore: verify_dart_semantic — int placeholder until asset probe; not a visual dp
      height:
          0, // ignore: verify_dart_semantic — int placeholder until asset probe; not a visual dp
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
