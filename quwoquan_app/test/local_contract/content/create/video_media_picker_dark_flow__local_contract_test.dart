import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';

void main() {
  group('video media picker dark flow', () {
    test('视频模式只保留视频分类与下一步语义', () {
      expect(
        mediaPickerCategoriesForEntryMode(MediaPickerEntryMode.video),
        isEmpty,
      );

      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.video,
        selectionCount: 1,
      );

      expect(actions, hasLength(1));
      expect(actions.single.action, CreateMediaPickerBottomAction.nextStep);
      expect(actions.single.label, '下一步(1)');
      expect(actions.single.label, isNot(UITextConstants.mediaPickerEditImage));
    });

    testWidgets('视频选择器展示现在开拍与全部视频并过滤图片', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_video('v1'), _image('i1')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: CreateMediaPickerPage(
            entryMode: MediaPickerEntryMode.video,
            maxSelection: 1,
            mediaPickerService: service,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.mediaPickerVideoTitle), findsOneWidget);
      expect(
        find.text(UITextConstants.mediaPickerVideoCameraEntry),
        findsWidgets,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-i1')),
        findsNothing,
      );
    });
  });
}

AssetPathEntity _album(String id, String name) {
  return AssetPathEntity(id: id, name: name, type: RequestType.video);
}

AssetEntity _video(String id) {
  return AssetEntity(
    id: id,
    typeInt: AssetType.video.index,
    width: 1080,
    height: 1920,
    duration: 8,
    createDateSecond: 1760000000,
  );
}

AssetEntity _image(String id) {
  return AssetEntity(
    id: id,
    typeInt: AssetType.image.index,
    width: 1200,
    height: 1600,
    createDateSecond: 1760000000,
  );
}

class _FakeMediaPickerService extends MediaPickerService {
  _FakeMediaPickerService({
    required this.albums,
    required this.assetsByAlbumId,
  });

  final List<AssetPathEntity> albums;
  final Map<String, List<AssetEntity>> assetsByAlbumId;

  @override
  Future<bool> ensurePhotoPermission() async {
    return true;
  }

  @override
  Future<List<AssetPathEntity>> loadAlbums({required RequestType type}) async {
    return albums;
  }

  @override
  Future<List<AssetEntity>> loadAssets({
    required AssetPathEntity album,
    required int page,
    required int pageSize,
  }) async {
    return assetsByAlbumId[album.id] ?? const <AssetEntity>[];
  }

  @override
  Future<int> loadAlbumAssetCount(AssetPathEntity album) async {
    return (assetsByAlbumId[album.id] ?? const <AssetEntity>[]).length;
  }

  @override
  Future<Uint8List?> loadAlbumCover(AssetPathEntity album) async {
    return Uint8List.fromList(_transparentPngBytes);
  }

  @override
  Future<Uint8List?> loadThumbnail(AssetEntity entity, {int size = 240}) async {
    return Uint8List.fromList(_transparentPngBytes);
  }
}

const _transparentPngBytes = <int>[
  137,
  80,
  78,
  71,
  13,
  10,
  26,
  10,
  0,
  0,
  0,
  13,
  73,
  72,
  68,
  82,
  0,
  0,
  0,
  1,
  0,
  0,
  0,
  1,
  8,
  6,
  0,
  0,
  0,
  31,
  21,
  196,
  137,
  0,
  0,
  0,
  13,
  73,
  68,
  65,
  84,
  120,
  156,
  99,
  248,
  207,
  192,
  240,
  31,
  0,
  5,
  0,
  1,
  255,
  137,
  153,
  61,
  29,
  0,
  0,
  0,
  0,
  73,
  69,
  78,
  68,
  174,
  66,
  96,
  130,
];
