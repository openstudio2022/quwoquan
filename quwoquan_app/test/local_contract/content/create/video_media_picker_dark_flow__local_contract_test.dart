import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/components/media/picker/one_tap_movie_composer.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';

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

    testWidgets('视频选择器以宫格展示拍视频、一键成片与全部视频，并过滤图片', (tester) async {
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
      expect(
        find.text(UITextConstants.mediaPickerVideoCameraEntry),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-one-tap-movie-tile')),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.mediaPickerOneTapMovie), findsOneWidget);
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
      final movieTopLeft = tester.getTopLeft(
        find.byKey(const ValueKey<String>('media-picker-one-tap-movie-tile')),
      );
      final videoTopLeft = tester.getTopLeft(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
      );
      expect(cameraTopLeft.dx, lessThan(movieTopLeft.dx));
      expect(movieTopLeft.dx, lessThan(videoTopLeft.dx));
      expect(cameraTopLeft.dy, videoTopLeft.dy);
    });

    testWidgets('一键成片选择图片后返回生成视频结果且不回停选择器', (tester) async {
      CreateMediaPickerResult? picked;
      final composer = _FakeOneTapMovieComposer();
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_video('v1'), _image('i1')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('open'),
              onPressed: () async {
                picked = await Navigator.of(context)
                    .push<CreateMediaPickerResult>(
                      CupertinoPageRoute<CreateMediaPickerResult>(
                        builder: (_) => CreateMediaPickerPage(
                          entryMode: MediaPickerEntryMode.video,
                          maxSelection: 1,
                          mediaPickerService: service,
                          oneTapMovieComposer: composer,
                        ),
                      ),
                    );
              },
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await _pumpMediaPickerFrame(tester);
      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-one-tap-movie-tile')),
      );
      await _pumpMediaPickerFrame(tester);

      expect(find.text(UITextConstants.mediaPickerPhotoTitle), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-i1')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('media-picker-asset-v1')),
        findsNothing,
      );

      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-asset-i1')),
      );
      await _pumpMediaPickerFrame(tester);
      await tester.tap(
        find.text(
          mediaPickerCompletionLabel(
            mode: MediaPickerEntryMode.image,
            selectionCount: 1,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.mediaPickerNextStep), findsOneWidget);
      await tester.tap(find.text(UITextConstants.mediaPickerNextStep));
      await tester.pumpAndSettle();

      expect(composer.images.map((item) => item.id), <String>['i1']);
      expect(picked, isNotNull);
      expect(picked!.openOneTapMovie, isTrue);
      expect(picked!.items, hasLength(1));
      expect(picked!.items.single.type, CreateMediaType.video);
      expect(picked!.items.single.source, CreateMediaSource.generated);
      expect(picked!.items.single.path, '/tmp/one_tap_movie.mp4');
      expect(picked!.items.single.durationMs, 3000);
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

class _FakeOneTapMovieComposer implements OneTapMovieComposer {
  List<CreateMediaItem> images = const <CreateMediaItem>[];

  @override
  Future<OneTapMovieComposeResult> compose({
    required List<CreateMediaItem> images,
  }) async {
    this.images = List<CreateMediaItem>.of(images);
    return OneTapMovieComposeResult(
      videoPath: '/tmp/one_tap_movie.mp4',
      durationMs: images.length * 3000,
      coverPath: '/tmp/one_tap_movie_cover.jpg',
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
