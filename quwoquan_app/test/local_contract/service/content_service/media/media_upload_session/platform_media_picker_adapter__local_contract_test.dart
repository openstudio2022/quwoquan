import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/platform_media_picker_adapter.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/runtime/platform/media/media_library_gateway.dart';

void main() {
  group('PlatformMediaPickerAdapter local contract', () {
    test(
      'maps platform albums and assets without leaking plugin types',
      () async {
        final gateway = _MediaLibraryGatewayDouble();
        final adapter = PlatformMediaPickerAdapter(gateway);

        final albums = await adapter.loadAlbums(
          type: MediaPickerRequestType.common,
        );
        final assets = await adapter.loadAssets(
          album: albums.single,
          page: 0,
          pageSize: 80,
        );

        expect(gateway.lastRequestType, PlatformMediaLibraryRequestType.common);
        expect(albums.single.requestType, MediaPickerRequestType.common);
        expect(albums.single.isAll, isTrue);
        expect(assets.map((asset) => asset.type), <MediaPickerAssetType>[
          MediaPickerAssetType.image,
          MediaPickerAssetType.video,
        ]);
        expect(assets.last.durationMs, 8000);
        expect(await adapter.loadAlbumAssetCount(albums.single), 2);
        expect(await adapter.loadAlbumCover(albums.single), isNotEmpty);
        expect(await adapter.loadThumbnail(assets.first), isNotEmpty);
      },
    );

    test('maps gif and video assets into canonical CreateMediaItem', () async {
      final gateway = _MediaLibraryGatewayDouble();
      final adapter = PlatformMediaPickerAdapter(gateway);
      final album = (await adapter.loadAlbums(
        type: MediaPickerRequestType.common,
      )).single;
      final assets = await adapter.loadAssets(
        album: album,
        page: 0,
        pageSize: 80,
      );

      final gif = await adapter.assetToMediaItem(assets.first);
      final video = await adapter.assetToMediaItem(assets.last);

      expect(gif?.type, CreateMediaType.gif);
      expect(gif?.path, '/media/image-one.gif');
      expect(video?.type, CreateMediaType.video);
      expect(video?.durationMs, 8000);
    });

    test('fails closed when platform cannot resolve a local file', () async {
      final gateway = _MediaLibraryGatewayDouble()..returnMissingPath = true;
      final adapter = PlatformMediaPickerAdapter(gateway);
      final album = (await adapter.loadAlbums(
        type: MediaPickerRequestType.image,
      )).single;
      final asset = (await adapter.loadAssets(
        album: album,
        page: 0,
        pageSize: 80,
      )).first;

      expect(await adapter.assetToMediaItem(asset), isNull);
    });

    test('uses injected clock for camera and generated media identity', () {
      final gateway = _MediaLibraryGatewayDouble();
      final now = DateTime.fromMillisecondsSinceEpoch(1760000000123);
      final adapter = PlatformMediaPickerAdapter(gateway, now: () => now);

      final item = adapter.fileToMediaItem(
        filePath: '/tmp/camera.jpg',
        source: CreateMediaSource.camera,
        type: CreateMediaType.image,
      );

      expect(item.id, 'camera-${now.microsecondsSinceEpoch}');
      expect(item.createdAtMs, now.millisecondsSinceEpoch);
      expect(item.path, '/tmp/camera.jpg');
    });
  });
}

final class _MediaLibraryGatewayDouble implements MediaLibraryGateway {
  PlatformMediaLibraryRequestType? lastRequestType;
  bool returnMissingPath = false;

  @override
  Future<List<PlatformMediaAlbumRef>> loadAlbums({
    required PlatformMediaLibraryRequestType type,
  }) async {
    lastRequestType = type;
    return const <PlatformMediaAlbumRef>[
      PlatformMediaAlbumRef(id: 'all', name: '全部', isAll: true),
    ];
  }

  @override
  Future<List<PlatformMediaAssetRef>> loadAssets({
    required String albumId,
    required int page,
    required int pageSize,
  }) async {
    return const <PlatformMediaAssetRef>[
      PlatformMediaAssetRef(
        id: 'image-one',
        type: PlatformMediaAssetType.image,
        mimeType: 'image/gif',
        width: 1200,
        height: 1600,
        durationMs: 0,
        createdAtMs: 1760000000000,
      ),
      PlatformMediaAssetRef(
        id: 'video-one',
        type: PlatformMediaAssetType.video,
        mimeType: 'video/mp4',
        width: 1080,
        height: 1920,
        durationMs: 8000,
        createdAtMs: 1760000001000,
      ),
    ];
  }

  @override
  Future<int> loadAlbumAssetCount(String albumId) async => 2;

  @override
  Future<Uint8List?> loadAlbumCover(String albumId) async {
    return Uint8List.fromList(<int>[1]);
  }

  @override
  Future<Uint8List?> loadThumbnail(String assetId, {required int size}) async {
    return Uint8List.fromList(<int>[2]);
  }

  @override
  Future<String?> loadLocalFilePath(String assetId) async {
    if (returnMissingPath) {
      return null;
    }
    return assetId == 'video-one'
        ? '/media/video-one.mp4'
        : '/media/image-one.gif';
  }
}
