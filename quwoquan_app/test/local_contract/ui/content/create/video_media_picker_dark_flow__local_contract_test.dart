import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';

final ImageEditorFilterRepository _filterRepository =
    ImageEditorFilterRepository(
      catalogLoader: () async => const ImageEditorFilterConfig(
        releaseId: 'test-filter-release',
        canonicalDigest:
            'b7285b97911eccf95828beb2dc8ba34cc47d2eb3a36957aba8a36564f8c468a3',
        categories: <ImageEditorFilterCategory>[
          ImageEditorFilterCategory(
            id: 'camera_photo',
            label: '相机',
            sort: 0,
            enabled: true,
          ),
        ],
        presets: <ImageEditorFilterPreset>[
          ImageEditorFilterPreset(
            id: 'original',
            categoryId: 'camera_photo',
            name: '原图',
            sort: 0,
            enabled: true,
            defaultStrength: 0,
            adjustments: ImageEditorFilterAdjustments(),
          ),
        ],
        recommendedFallbackPresetIds: <String>['original'],
      ),
    );

void main() {
  group('video media picker dark flow', () {
    setUp(() {
      AppPermissionCoordinator.instance.ensureLifecycleAttached();
      AppPermissionCoordinator.instance.phaseReaders[AppPermissionKind.photos] =
          () async => AppPermissionPhase.granted;
      AppPermissionCoordinator.instance.grantCheckers[AppPermissionKind
          .photos] = () async =>
          true;
      AppPermissionCoordinator.instance.requesters[AppPermissionKind.photos] =
          () async => true;
    });

    tearDown(() {
      AppPermissionCoordinator.instance.phaseReaders.remove(
        AppPermissionKind.photos,
      );
      AppPermissionCoordinator.instance.grantCheckers.remove(
        AppPermissionKind.photos,
      );
      AppPermissionCoordinator.instance.requesters.remove(
        AppPermissionKind.photos,
      );
      AppPermissionCoordinator.instance.clearSession();
    });

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

    testWidgets('视频选择器以宫格展示拍视频与全部视频，并过滤图片', (tester) async {
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
            filterRepository: _filterRepository,
            mediaPickerService: service,
          ),
        ),
      );
      await _pumpMediaPickerFrame(tester);

      expect(find.text(UITextConstants.mediaPickerVideoTitle), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('media-picker-video-camera-hero')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-camera-tile')),
        findsOneWidget,
      );
      final cameraTile = tester.widget<Container>(
        find.descendant(
          of: find.byKey(const ValueKey<String>('media-picker-camera-tile')),
          matching: find.byType(Container),
        ),
      );
      final cameraDecoration = cameraTile.decoration! as BoxDecoration;
      expect(cameraDecoration.color, isNot(AppColors.black));
      expect(cameraDecoration.border, isNotNull);
      expect(
        find.text(UITextConstants.mediaPickerVideoCameraEntry),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-one-tap-movie-tile')),
        findsNothing,
      );
      expect(find.text(UITextConstants.mediaPickerOneTapMovie), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-i1')),
        findsNothing,
      );

      final cameraTopLeft = tester.getTopLeft(
        find.byKey(const ValueKey<String>('media-picker-camera-tile')),
      );
      final videoTopLeft = tester.getTopLeft(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
      );
      expect(cameraTopLeft.dx, lessThan(videoTopLeft.dx));
      expect(cameraTopLeft.dy, videoTopLeft.dy);
    });
  });
}

Future<void> _pumpMediaPickerFrame(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 700));
  await tester.pump();
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

  @override
  Future<CreateMediaItem?> assetToMediaItem(
    AssetEntity entity, {
    CreateMediaSource source = CreateMediaSource.album,
  }) async {
    return CreateMediaItem(
      id: entity.id,
      path: entity.type == AssetType.video
          ? '/tmp/${entity.id}.mp4'
          : '/tmp/${entity.id}.jpg',
      type: entity.type == AssetType.video
          ? CreateMediaType.video
          : CreateMediaType.image,
      source: source,
      width: entity.width,
      height: entity.height,
      durationMs: entity.duration * 1000,
      createdAtMs: (entity.createDateSecond ?? 0) * 1000,
    );
  }

  @override
  CreateMediaItem fileToMediaItem({
    required String filePath,
    required CreateMediaSource source,
    required CreateMediaType type,
  }) {
    return CreateMediaItem(
      id: filePath,
      path: filePath,
      type: type,
      source: source,
      width: type == CreateMediaType.video ? 1080 : 1200,
      height: type == CreateMediaType.video ? 1920 : 1600,
    );
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
