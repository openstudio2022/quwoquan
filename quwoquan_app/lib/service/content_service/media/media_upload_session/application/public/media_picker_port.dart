// MediaUploadSession 的跨对象公开媒体选择端口。
import 'dart:typed_data';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';

/// 业务选择器向平台相册请求的媒体范围。
enum MediaPickerRequestType { image, video, common }

/// 平台媒体类型在业务边界内的稳定表达，避免 presentation 泄漏插件类型。
enum MediaPickerAssetType { image, video, other }

final class MediaPickerAlbumRef {
  const MediaPickerAlbumRef({
    required this.id,
    required this.name,
    required this.requestType,
    this.isAll = false,
  });

  final String id;
  final String name;
  final MediaPickerRequestType requestType;
  final bool isAll;
}

final class MediaPickerAssetRef {
  const MediaPickerAssetRef({
    required this.id,
    required this.type,
    required this.width,
    required this.height,
    required this.durationMs,
    required this.createdAtMs,
    this.mimeType = '',
  });

  final String id;
  final MediaPickerAssetType type;
  final String mimeType;
  final int width;
  final int height;
  final int durationMs;
  final int createdAtMs;
}

/// media_upload_session 的可测试平台相册端口。
///
/// production adapter 负责把纯平台引用映射为 [CreateMediaItem]；Widget 测试只需
/// 提供 suite-local typed double，不再构造 `photo_manager` 实体。
abstract interface class MediaPickerPort {
  Future<List<MediaPickerAlbumRef>> loadAlbums({
    required MediaPickerRequestType type,
  });

  Future<List<MediaPickerAssetRef>> loadAssets({
    required MediaPickerAlbumRef album,
    required int page,
    required int pageSize,
  });

  Future<int> loadAlbumAssetCount(MediaPickerAlbumRef album);

  Future<Uint8List?> loadAlbumCover(MediaPickerAlbumRef album);

  Future<Uint8List?> loadThumbnail(MediaPickerAssetRef asset, {int size = 240});

  Future<CreateMediaItem?> assetToMediaItem(
    MediaPickerAssetRef asset, {
    CreateMediaSource source = CreateMediaSource.album,
  });

  CreateMediaItem fileToMediaItem({
    required String filePath,
    required CreateMediaSource source,
    required CreateMediaType type,
  });
}
