// spec_ref: specs/feature-tree/discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md#gwt-001
library;

import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_repository.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_picker_port.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_page.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_presentation.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart' show MediaText;
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakePickerImageEditorPage extends StatelessWidget {
  const _FakePickerImageEditorPage({required this.result});

  final Map<String, Object> result;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      child: Center(
        child: CupertinoButton(
          key: const ValueKey<String>('fake-picker-editor-confirm'),
          onPressed: () => Navigator.of(context).pop(result),
          child: const Text('确认编辑'),
        ),
      ),
    );
  }
}

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

Future<String> _fakeCapture() async => '/tmp/captured.jpg';

Future<String?> _fakePickerEditor(
  BuildContext context,
  CameraPhotoEditorRequest request,
) async {
  expect(request.caller, CameraPhotoCaller.picker);
  expect(request.entrySource, CameraPhotoEntrySource.photoPicker);
  return '/tmp/picker-camera-edited.jpg';
}

class _FakeFilterRepository extends ImageEditorFilterRepository {
  @override
  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets() async {
    return const <ImageEditorFilterPreset>[
      ImageEditorFilterPreset(
        id: 'original',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: MediaText.imageEditOriginal,
        sort: 1,
        enabled: true,
        defaultStrength: 0,
        adjustments: ImageEditorFilterAdjustments(),
      ),
    ];
  }
}

class _EmptyMediaPickerPort implements MediaPickerPort {
  @override
  Future<List<MediaPickerAlbumRef>> loadAlbums({
    required MediaPickerRequestType type,
  }) async {
    return <MediaPickerAlbumRef>[
      const MediaPickerAlbumRef(
        id: 'recent',
        name: '最近项目',
        requestType: MediaPickerRequestType.image,
      ),
    ];
  }

  @override
  Future<List<MediaPickerAssetRef>> loadAssets({
    required MediaPickerAlbumRef album,
    required int page,
    required int pageSize,
  }) async {
    return const <MediaPickerAssetRef>[];
  }

  @override
  Future<int> loadAlbumAssetCount(MediaPickerAlbumRef album) async => 0;

  @override
  Future<Uint8List?> loadAlbumCover(MediaPickerAlbumRef album) async => null;

  @override
  Future<Uint8List?> loadThumbnail(
    MediaPickerAssetRef asset, {
    int size = 240,
  }) async => null;

  @override
  Future<CreateMediaItem?> assetToMediaItem(
    MediaPickerAssetRef asset, {
    CreateMediaSource source = CreateMediaSource.album,
  }) async => null;

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
    );
  }
}

void _usePhoneSurface(WidgetTester tester) {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    AppPermissionCoordinator.instance.ensureLifecycleAttached();
    AppPermissionCoordinator.instance.phaseReaders[AppPermissionKind.photos] =
        () async => AppPermissionPhase.granted;
    AppPermissionCoordinator.instance.grantCheckers[AppPermissionKind.photos] =
        () async => true;
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

  testWidgets('图片选择器首格拍照会进入编辑器并回 picker 追加', (tester) async {
    _usePhoneSurface(tester);
    CreateMediaPickerResult? result;
    await tester.pumpWidget(
      ProviderScope(
        child: CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('open picker'),
              onPressed: () async {
                result = await Navigator.of(context)
                    .push<CreateMediaPickerResult>(
                      CupertinoPageRoute<CreateMediaPickerResult>(
                        builder: (_) => CreateMediaPickerPage(
                          entryMode: MediaPickerEntryMode.image,
                          maxSelection: 9,
                          filterRepository: _FakeFilterRepository(),
                          mediaPickerPort: _EmptyMediaPickerPort(),
                          imageEditorBuilder: (context, request) =>
                              _FakePickerImageEditorPage(
                                result: <String, Object>{
                                  'index': request.index,
                                  'path': request.initialPath,
                                  'paths': request.imagePaths,
                                  'action': 'continueToCreate',
                                },
                              ),
                          cameraBuilder:
                              (
                                context,
                                caller,
                                entrySource,
                                selectedCountBeforeCapture,
                              ) => CameraCapturePage(
                                initialMode: MediaPickerEntryMode.image,
                                allowVideoMode: false,
                                caller: caller,
                                entrySource: entrySource,
                                selectedCountBeforeCapture:
                                    selectedCountBeforeCapture,
                                previewBuilder: _fakePreview,
                                previewCameraDescriptions:
                                    _fakeBackAndFrontCameras,
                                filterRepository: _FakeFilterRepository(),
                                photoCapture: _fakeCapture,
                                imageEditorLauncher: _fakePickerEditor,
                              ),
                        ),
                      ),
                    );
              },
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open picker'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(
      find.byKey(const ValueKey<String>('media-picker-camera-tile')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text(MediaText.cameraUsePhoto));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(
      find.text(
        mediaPickerCompletionLabel(
          mode: MediaPickerEntryMode.image,
          selectionCount: 1,
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(
      find.byKey(const ValueKey<String>('fake-picker-editor-confirm')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(result?.items.map((item) => item.path), <String>[
      '/tmp/picker-camera-edited.jpg',
    ]);
  });
}
