import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

void main() {
  testWidgets('高保视频摄像页顶栏/蓝色录像按钮/三按钮对称与滤镜几何', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.video,
          allowVideoMode: true,
          previewBuilder: _fakePreview,
          previewCameraDescriptions: _fakeBackAndFrontCameras,
          filterRepository: _FakeFilterRepository(),
          microphonePermissionRequest: _grantedMicrophone,
          videoRecordingStart: _fakeRecordingStart,
          videoRecordingStop: _fakeRecordingStop,
          videoPreviewBuilder: _fakeVideoPreview,
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 顶栏复用图片高保 56pt 几何。
    expect(
      tester
          .getSize(find.byKey(const ValueKey<String>('camera-top-bar')))
          .height,
      56,
    );

    // 取景区与图片高保一致的沉浸式高度。
    final previewSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-preview-stage')),
    );
    expect(previewSize.height, greaterThan(300));

    // 蓝色录像主按钮 74pt。
    final recordSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    expect(recordSize.width, 74);
    expect(recordSize.height, 74);

    // 底部三按钮：滤镜 / 录像 / 翻转，左右对称。
    final filterCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-filter-action')),
    );
    final recordCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    final rotateCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
    );
    expect(filterCenter.dx, lessThan(recordCenter.dx));
    expect(rotateCenter.dx, greaterThan(recordCenter.dx));
    expect(
      (recordCenter.dx - filterCenter.dx).abs(),
      closeTo((rotateCenter.dx - recordCenter.dx).abs(), 1),
    );

    // 展开滤镜：滤镜条在录像按钮下方且 56pt 缩略图，录像按钮仍居中不偏移。
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-filter-action')),
    );
    await tester.pumpAndSettle();

    final filterStripTop = tester
        .getTopLeft(find.byKey(const ValueKey<String>('camera-filter-strip')))
        .dy;
    final recordBottom = tester
        .getBottomLeft(
          find.byKey(const ValueKey<String>('camera-record-action')),
        )
        .dy;
    expect(filterStripTop, greaterThan(recordBottom));

    final filterTileSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-filter-original')),
    );
    expect(filterTileSize.width, 56);
    expect(filterTileSize.height, greaterThanOrEqualTo(56));

    final recordCenterAfter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    expect(recordCenterAfter.dx, recordCenter.dx);
  });
}

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
      ImageEditorFilterPreset(
        id: 'cool',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: MediaText.imageEditCameraCool,
        sort: 2,
        enabled: true,
        defaultStrength: 80,
        adjustments: ImageEditorFilterAdjustments(temperature: -12),
      ),
    ];
  }
}
