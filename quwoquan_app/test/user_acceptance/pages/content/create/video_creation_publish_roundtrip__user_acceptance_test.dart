import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_page.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  group('video creation publish roundtrip', () {
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

    testWidgets('拍视频 -> 摄像模式 -> 录制 -> 预览确认 -> 下一步 回填视频到创作选择', (tester) async {
      final service = _FakeMediaPickerService(
        albums: <AssetPathEntity>[_album('recent', '最近项目')],
        assetsByAlbumId: <String, List<AssetEntity>>{
          'recent': <AssetEntity>[_video('v1')],
        },
      );

      await tester.pumpWidget(
        CupertinoApp(
          home: CreateMediaPickerPage(
            entryMode: MediaPickerEntryMode.video,
            maxSelection: 1,
            mediaPickerService: service,
            cameraBuilder: (context, caller, entrySource, selectedCount) {
              return CameraCapturePage(
                initialMode: MediaPickerEntryMode.video,
                allowVideoMode: true,
                caller: caller,
                entrySource: entrySource,
                selectedCountBeforeCapture: selectedCount,
                previewBuilder: _fakePreview,
                previewCameraDescriptions: _fakeBackAndFrontCameras,
                filterRepository: _FakeFilterRepository(),
                microphonePermissionRequest: _grantedMicrophone,
                videoRecordingStart: _fakeRecordingStart,
                videoRecordingStop: _fakeRecordingStop,
                videoPreviewBuilder: _fakeVideoPreview,
              );
            },
          ),
        ),
      );
      await _pumpMediaPickerFrame(tester);

      // 进入视频选择器后没有任何已选视频。
      expect(_selectedThumbFinder, findsNothing);

      // 点击「拍视频」宫格入口进入摄像模式（不是拍照壳）。
      await tester.tap(
        find.byKey(const ValueKey<String>('media-picker-camera-tile')),
      );
      await _pumpRouteFrame(tester);
      expect(find.text(UITextConstants.cameraVideoModeTitle), findsOneWidget);
      expect(find.text(UITextConstants.cameraPhotoModeTitle), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('camera-record-action')),
        findsOneWidget,
      );

      // 录制越过最短时长后停止，进入预览确认。
      await tester.tap(
        find.byKey(const ValueKey<String>('camera-record-action')),
      );
      for (var i = 0; i < 4; i++) {
        await tester.pump(const Duration(milliseconds: 400));
      }
      await tester.tap(
        find.byKey(const ValueKey<String>('camera-record-action')),
      );
      await tester.pump();
      await tester.pump();
      await _pumpRouteFrame(tester);
      expect(find.text(UITextConstants.cameraVideoNext), findsOneWidget);

      // 「下一步」把视频结果回填到创作选择，回到视频选择器。
      await tester.tap(
        find.byKey(const ValueKey<String>('camera-use-video-action')),
      );
      await _pumpMediaPickerFrame(tester);

      expect(find.text(UITextConstants.mediaPickerVideoTitle), findsOneWidget);
      expect(_selectedThumbFinder, findsOneWidget);
      expect(
        find.text(
          mediaPickerCompletionLabel(
            mode: MediaPickerEntryMode.video,
            selectionCount: 1,
          ),
        ),
        findsOneWidget,
      );
    });

    test('录制视频继续走发布 payload：远端视频与自动首帧封面无本地路径泄漏', () async {
      final media = RecordingContentMediaFacet();
      final fileStorage = _RoundtripFileStorageGateway(<String, List<int>>{
        '/tmp/recorded.mp4': <int>[1, 2, 3, 4],
      });
      final uploads = <String>[];
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.video,
            videoPath: '/tmp/recorded.mp4',
            originalVideoPath: '/tmp/recorded.mp4',
            videoDurationMs: 1600,
            videoCoverStrategy: 'first_frame',
            videoWidth: 1080,
            videoHeight: 1920,
            body: '刚录制的视频，直接发布。',
          );

      final prepared = await buildCreatePostPayloadWithRemoteImageMedia(
        media: media,
        fileStorageGateway: fileStorage,
        state: state,
        uploadObject:
            (
              uri,
              bytes, {
              required contentType,
              required expectedSha256,
            }) async {
              uploads.add(contentType);
            },
      );
      await media.bindPostMediaAssets(
        BindContentPostMediaAssetsCommand(
          postId: 'post_video_roundtrip',
          assetIds: prepared.mediaAssetIds,
        ),
      );

      expect(prepared.payload['contentType'], 'video');
      expect(uploads, <String>['video/mp4']);
      expect(media.selectedAutoCoverMediaIds, <String>['video_asset_1']);
      expect(
        prepared.payload['videoUrl'],
        'https://cdn.quwoquan.test/video_asset_1.mp4',
      );
      expect(prepared.payload['coverStrategy'], 'first_frame');
      expect(
        prepared.payload['thumbnailUrl'],
        'https://cdn.quwoquan.test/video_asset_1_cover.jpg',
      );
      expect(
        prepared.payload['coverUrl'],
        'https://cdn.quwoquan.test/video_asset_1_cover.jpg',
      );
      expect(prepared.payload['durationMs'], 1600);
      expect(prepared.payload['width'], 1080);
      expect(prepared.payload['height'], 1920);
      expect(prepared.payload.values.toString(), isNot(contains('/tmp/')));
      expect(media.boundAssetIds, prepared.mediaAssetIds);
    });
  });
}

final Finder _selectedThumbFinder = find.byWidgetPredicate(
  (widget) =>
      widget.key is ValueKey<String> &&
      (widget.key! as ValueKey<String>).value.startsWith(
        'media-picker-selected-thumb-',
      ),
);

Future<bool> _grantedMicrophone() async => true;

Future<void> _fakeRecordingStart() async {}

Future<String> _fakeRecordingStop() async => '/tmp/recorded.mp4';

const _fakeBackAndFrontCameras = <CameraDescription>[
  CameraDescription(
    name: 'back',
    lensDirection: CameraLensDirection.back,
    sensorOrientation: 90,
  ),
  CameraDescription(
    name: 'front',
    lensDirection: CameraLensDirection.front,
    sensorOrientation: 270,
  ),
];

Widget _fakePreview(BuildContext context) {
  return const ColoredBox(color: CupertinoColors.black);
}

Widget _fakeVideoPreview(BuildContext context, String path) {
  return const ColoredBox(
    key: ValueKey<String>('fake-video-preview'),
    color: CupertinoColors.black,
  );
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

class _FakeFilterRepository extends ImageEditorFilterRepository {
  @override
  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets() async {
    return const <ImageEditorFilterPreset>[
      ImageEditorFilterPreset(
        id: 'original',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: UITextConstants.imageEditOriginal,
        sort: 1,
        enabled: true,
        defaultStrength: 0,
        params: <String, double>{},
      ),
    ];
  }
}

class _FakeMediaPickerService extends MediaPickerService {
  _FakeMediaPickerService({
    required this.albums,
    required this.assetsByAlbumId,
  });

  final List<AssetPathEntity> albums;
  final Map<String, List<AssetEntity>> assetsByAlbumId;

  @override
  Future<bool> ensurePhotoPermission() async => true;

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

class _RoundtripFileStorageGateway implements FileStorageGateway {
  const _RoundtripFileStorageGateway(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async => '/tmp/support';

  @override
  Future<String> temporaryPath() async => '/tmp';

  @override
  Future<bool> exists(String path) async => bytesByPath.containsKey(path);

  @override
  Future<String> readAsString(String path) async => '';

  @override
  Future<void> writeAsString(String path, String contents) async {}

  @override
  Future<List<int>> readAsBytes(String path) async => bytesByPath[path]!;

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];
}

Future<void> _pumpMediaPickerFrame(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 700));
  await tester.pump();
}

Future<void> _pumpRouteFrame(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
  await tester.pump();
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
