import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/adapters/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

void main() {
  testWidgets('高保拍照页关键几何满足顶栏快门和滤镜尺寸约束', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.image,
          allowVideoMode: false,
          previewBuilder: _fakePreview,
          previewCameraDescriptions: _fakeBackAndFrontCameras,
          filterRepository: _FakeFilterRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester
          .getSize(find.byKey(const ValueKey<String>('camera-top-bar')))
          .height,
      56,
    );
    final previewSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-preview-stage')),
    );
    expect(previewSize.height, greaterThan(300));

    final shutterSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    expect(shutterSize.width, 74);
    expect(shutterSize.height, 74);

    final filterCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-filter-action')),
    );
    final shutterCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    final rotateCenter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
    );
    expect(filterCenter.dx, lessThan(shutterCenter.dx));
    expect(rotateCenter.dx, greaterThan(shutterCenter.dx));
    expect(
      (shutterCenter.dx - filterCenter.dx).abs(),
      closeTo((rotateCenter.dx - shutterCenter.dx).abs(), 1),
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-filter-action')),
    );
    await tester.pumpAndSettle();

    final filterStripTop = tester
        .getTopLeft(find.byKey(const ValueKey<String>('camera-filter-strip')))
        .dy;
    final shutterBottom = tester
        .getBottomLeft(
          find.byKey(const ValueKey<String>('camera-capture-action')),
        )
        .dy;
    expect(filterStripTop, greaterThan(shutterBottom));

    final filterTileSize = tester.getSize(
      find.byKey(const ValueKey<String>('camera-filter-original')),
    );
    expect(filterTileSize.width, 56);
    expect(filterTileSize.height, greaterThanOrEqualTo(56));
    final shutterCenterAfter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    expect(shutterCenterAfter.dx, shutterCenter.dx);
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
      ImageEditorFilterPreset(
        id: 'vivid',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: MediaText.imageEditCameraVivid,
        sort: 2,
        enabled: true,
        defaultStrength: 80,
        adjustments: ImageEditorFilterAdjustments(saturation: 12),
      ),
    ];
  }
}
