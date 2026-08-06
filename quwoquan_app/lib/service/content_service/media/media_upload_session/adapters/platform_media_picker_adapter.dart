import 'dart:typed_data';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/runtime/platform/media/media_library_gateway.dart';

final class PlatformMediaPickerAdapter implements MediaPickerPort {
  PlatformMediaPickerAdapter(this._mediaLibrary, {DateTime Function()? now})
    : _now = now ?? DateTime.now;

  final MediaLibraryGateway _mediaLibrary;
  final DateTime Function() _now;

  @override
  Future<List<MediaPickerAlbumRef>> loadAlbums({
    required MediaPickerRequestType type,
  }) async {
    final albums = await _mediaLibrary.loadAlbums(
      type: switch (type) {
        MediaPickerRequestType.image => PlatformMediaLibraryRequestType.image,
        MediaPickerRequestType.video => PlatformMediaLibraryRequestType.video,
        MediaPickerRequestType.common => PlatformMediaLibraryRequestType.common,
      },
    );
    return albums
        .map(
          (album) => MediaPickerAlbumRef(
            id: album.id,
            name: album.name,
            requestType: type,
            isAll: album.isAll,
          ),
        )
        .toList(growable: false);
  }

  @override
  Future<List<MediaPickerAssetRef>> loadAssets({
    required MediaPickerAlbumRef album,
    required int page,
    required int pageSize,
  }) async {
    final assets = await _mediaLibrary.loadAssets(
      albumId: album.id,
      page: page,
      pageSize: pageSize,
    );
    return assets.map(_assetRef).toList(growable: false);
  }

  @override
  Future<int> loadAlbumAssetCount(MediaPickerAlbumRef album) {
    return _mediaLibrary.loadAlbumAssetCount(album.id);
  }

  @override
  Future<Uint8List?> loadAlbumCover(MediaPickerAlbumRef album) {
    return _mediaLibrary.loadAlbumCover(album.id);
  }

  @override
  Future<Uint8List?> loadThumbnail(
    MediaPickerAssetRef asset, {
    int size = 240,
  }) {
    return _mediaLibrary.loadThumbnail(asset.id, size: size);
  }

  @override
  Future<CreateMediaItem?> assetToMediaItem(
    MediaPickerAssetRef asset, {
    CreateMediaSource source = CreateMediaSource.album,
  }) async {
    final path = await _mediaLibrary.loadLocalFilePath(asset.id);
    if (path == null) {
      return null;
    }
    return CreateMediaItem(
      id: asset.id,
      path: path,
      type: _mediaType(asset),
      source: source,
      width: asset.width,
      height: asset.height,
      durationMs: asset.durationMs,
      createdAtMs: asset.createdAtMs,
    );
  }

  @override
  CreateMediaItem fileToMediaItem({
    required String filePath,
    required CreateMediaSource source,
    required CreateMediaType type,
  }) {
    final now = _now();
    return CreateMediaItem(
      id: '${source.name}-${now.microsecondsSinceEpoch}',
      path: filePath,
      type: type,
      source: source,
      createdAtMs: now.millisecondsSinceEpoch,
    );
  }

  MediaPickerAssetRef _assetRef(PlatformMediaAssetRef asset) {
    return MediaPickerAssetRef(
      id: asset.id,
      type: switch (asset.type) {
        PlatformMediaAssetType.image => MediaPickerAssetType.image,
        PlatformMediaAssetType.video => MediaPickerAssetType.video,
        PlatformMediaAssetType.other => MediaPickerAssetType.other,
      },
      mimeType: asset.mimeType,
      width: asset.width,
      height: asset.height,
      durationMs: asset.durationMs,
      createdAtMs: asset.createdAtMs,
    );
  }

  CreateMediaType _mediaType(MediaPickerAssetRef asset) {
    if (asset.type == MediaPickerAssetType.video) {
      return CreateMediaType.video;
    }
    if (asset.mimeType.toLowerCase().contains('gif')) {
      return CreateMediaType.gif;
    }
    return CreateMediaType.image;
  }
}
