import 'dart:typed_data';

/// runtime/platform 对系统媒体库的纯类型边界；不得引用任何业务 domain 类型。
enum PlatformMediaLibraryRequestType { image, video, common }

enum PlatformMediaAssetType { image, video, other }

final class PlatformMediaAlbumRef {
  const PlatformMediaAlbumRef({
    required this.id,
    required this.name,
    required this.isAll,
  });

  final String id;
  final String name;
  final bool isAll;
}

final class PlatformMediaAssetRef {
  const PlatformMediaAssetRef({
    required this.id,
    required this.type,
    required this.mimeType,
    required this.width,
    required this.height,
    required this.durationMs,
    required this.createdAtMs,
  });

  final String id;
  final PlatformMediaAssetType type;
  final String mimeType;
  final int width;
  final int height;
  final int durationMs;
  final int createdAtMs;
}

abstract interface class MediaLibraryGateway {
  Future<List<PlatformMediaAlbumRef>> loadAlbums({
    required PlatformMediaLibraryRequestType type,
  });

  Future<List<PlatformMediaAssetRef>> loadAssets({
    required String albumId,
    required int page,
    required int pageSize,
  });

  Future<int> loadAlbumAssetCount(String albumId);

  Future<Uint8List?> loadAlbumCover(String albumId);

  Future<Uint8List?> loadThumbnail(String assetId, {required int size});

  Future<String?> loadLocalFilePath(String assetId);
}
