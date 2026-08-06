import 'dart:typed_data';

import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/runtime/platform/media/media_library_gateway.dart';

/// `photo_manager` 的唯一相册实现；对上只暴露 runtime 纯引用。
final class PhotoManagerMediaLibraryGateway implements MediaLibraryGateway {
  static const int _coverProbePageSize = 1;
  static const int _coverThumbnailPixelSize = 160;

  final Map<String, AssetPathEntity> _albums = <String, AssetPathEntity>{};
  final Map<String, AssetEntity> _assets = <String, AssetEntity>{};

  @override
  Future<List<PlatformMediaAlbumRef>> loadAlbums({
    required PlatformMediaLibraryRequestType type,
  }) async {
    final entities = await PhotoManager.getAssetPathList(
      type: switch (type) {
        PlatformMediaLibraryRequestType.image => RequestType.image,
        PlatformMediaLibraryRequestType.video => RequestType.video,
        PlatformMediaLibraryRequestType.common => RequestType.common,
      },
      hasAll: true,
      filterOption: FilterOptionGroup(
        imageOption: const FilterOption(needTitle: true),
      ),
    );
    for (final entity in entities) {
      _albums[entity.id] = entity;
    }
    return entities
        .map(
          (entity) => PlatformMediaAlbumRef(
            id: entity.id,
            name: entity.name,
            isAll: entity.isAll,
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<PlatformMediaAssetRef>> loadAssets({
    required String albumId,
    required int page,
    required int pageSize,
  }) async {
    final album = _album(albumId);
    final entities = await album.getAssetListPaged(page: page, size: pageSize);
    for (final entity in entities) {
      _assets[entity.id] = entity;
    }
    return entities.map(_assetRef).toList(growable: false);
  }

  @override
  Future<int> loadAlbumAssetCount(String albumId) {
    return _album(albumId).assetCountAsync;
  }

  @override
  Future<Uint8List?> loadAlbumCover(String albumId) async {
    final entities = await _album(
      albumId,
    ).getAssetListPaged(page: 0, size: _coverProbePageSize);
    if (entities.isEmpty) {
      return null;
    }
    final entity = entities.first;
    _assets[entity.id] = entity;
    return entity.thumbnailDataWithSize(
      const ThumbnailSize.square(_coverThumbnailPixelSize),
    );
  }

  @override
  Future<Uint8List?> loadThumbnail(String assetId, {required int size}) {
    return _asset(assetId).thumbnailDataWithSize(ThumbnailSize.square(size));
  }

  @override
  Future<String?> loadLocalFilePath(String assetId) async {
    final file = await _asset(assetId).file;
    final path = file?.path.trim();
    return path == null || path.isEmpty ? null : path;
  }

  AssetPathEntity _album(String id) {
    final entity = _albums[id];
    if (entity == null) {
      throw StateError('media album was not loaded: $id');
    }
    return entity;
  }

  AssetEntity _asset(String id) {
    final entity = _assets[id];
    if (entity == null) {
      throw StateError('media asset was not loaded: $id');
    }
    return entity;
  }

  PlatformMediaAssetRef _assetRef(AssetEntity entity) {
    return PlatformMediaAssetRef(
      id: entity.id,
      type: switch (entity.type) {
        AssetType.image => PlatformMediaAssetType.image,
        AssetType.video => PlatformMediaAssetType.video,
        _ => PlatformMediaAssetType.other,
      },
      mimeType: entity.mimeType ?? '',
      width: entity.width,
      height: entity.height,
      durationMs: entity.duration * 1000,
      createdAtMs: entity.createDateTime.millisecondsSinceEpoch,
    );
  }
}
