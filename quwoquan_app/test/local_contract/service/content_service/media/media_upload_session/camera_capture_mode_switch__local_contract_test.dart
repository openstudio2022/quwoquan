import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_repository.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_creation_launch_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';

void main() {
  testWidgets('switchable 相机默认拍照并可切换到录像', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.image,
          modePolicy: CameraCaptureModePolicy.switchable,
          previewBuilder: _fakePreview,
          previewCameraDescriptions: _fakeBackAndFrontCameras,
          filterRepository: _FakeFilterRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraPhotoModeTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('camera-mode-switcher')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-mode-photo')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-mode-video')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey<String>('camera-mode-video')));
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraVideoModeTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey<String>('camera-mode-photo')));
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraPhotoModeTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsOneWidget,
    );
  });
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
