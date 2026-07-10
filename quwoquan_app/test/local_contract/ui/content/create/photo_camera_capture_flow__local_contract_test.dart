import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/camera/camera_session_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

void main() {
  testWidgets('图片拍摄入口隐藏录像模式', (tester) async {
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

    expect(find.text(UITextConstants.cameraPhotoModeTitle), findsOneWidget);
    expect(find.text(UITextConstants.cameraVideoMode), findsNothing);
    expect(find.text(UITextConstants.cameraFilter), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
      findsOneWidget,
    );
  });

  testWidgets('相机不可用时展示深色错误语义且隐藏无意义拍照与切换按钮', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        theme: CupertinoThemeData(brightness: Brightness.light),
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.image,
          allowVideoMode: false,
          cameraDiscovery: _noAvailableCameras,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.cameraUnavailableTitle), findsOneWidget);
    expect(find.text(UITextConstants.cameraUnavailable), findsOneWidget);
    expect(
      find.text(UITextConstants.cameraUnavailableRecovery),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
      findsNothing,
    );
    final titleFinder = find.text(UITextConstants.cameraUnavailableTitle);
    final titleContext = tester.element(titleFinder);
    expect(MediaQuery.of(titleContext).platformBrightness, Brightness.dark);
    expect(CupertinoTheme.of(titleContext).brightness, Brightness.dark);
    expect(find.text(UITextConstants.back), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });

  testWidgets('图片拍摄确认态不展示录像切换和右上角相机切换', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.image,
          allowVideoMode: false,
          initialCapturedPhotoPath: '/tmp/captured.jpg',
          cameraDiscovery: _noAvailableCameras,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.cameraPhotoModeTitle), findsOneWidget);
    expect(find.text(UITextConstants.cameraVideoMode), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
      findsNothing,
    );
    expect(find.text(UITextConstants.cameraRetakePhoto), findsOneWidget);
    expect(find.text(UITextConstants.cameraUsePhoto), findsOneWidget);
  });

  testWidgets('拍照后确认态支持重新拍摄', (tester) async {
    await tester.pumpWidget(
      const CupertinoApp(
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.image,
          allowVideoMode: false,
          initialCapturedPhotoPath: '/tmp/captured.jpg',
          cameraDiscovery: _noAvailableCameras,
        ),
      ),
    );
    await tester.pump();

    expect(find.text(UITextConstants.cameraRetakePhoto), findsOneWidget);
    expect(find.text(UITextConstants.cameraUsePhoto), findsOneWidget);

    await tester.tap(find.text(UITextConstants.cameraRetakePhoto));
    await tester.pump();

    expect(find.text(UITextConstants.cameraRetakePhoto), findsNothing);
    expect(find.text(UITextConstants.cameraUsePhoto), findsNothing);
  });

  testWidgets('滤镜条支持展开选择且快门保持居中', (tester) async {
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

    final shutterCenterBefore = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-filter-action')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('camera-filter-strip')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-filter-cool')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey<String>('camera-filter-cool')));
    await tester.pump();

    final shutterCenterAfter = tester.getCenter(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    expect(shutterCenterAfter.dx, shutterCenterBefore.dx);
  });

  testWidgets('闪光灯单击切换开关且切前置后置灰关闭', (tester) async {
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

    await tester.tap(find.byKey(const ValueKey<String>('camera-flash-action')));
    await tester.pumpAndSettle();
    expect(find.byIcon(CupertinoIcons.bolt_fill), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.bolt_slash_fill), findsNothing);

    await tester.tap(find.byKey(const ValueKey<String>('camera-flash-action')));
    await tester.pumpAndSettle();
    expect(find.byIcon(CupertinoIcons.bolt_slash_fill), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('camera-flash-action')));
    await tester.pumpAndSettle();
    expect(find.byIcon(CupertinoIcons.bolt_fill), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
    );
    await tester.pumpAndSettle();

    final flashButton = tester.widget<CupertinoButton>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('camera-flash-action')),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(flashButton.onPressed, isNull);
    expect(find.byIcon(CupertinoIcons.bolt_slash_fill), findsOneWidget);
  });

  testWidgets('fake 拍照进入预览并通过编辑器返回图片拍摄结果', (tester) async {
    CameraCaptureResult? result;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open camera'),
            onPressed: () async {
              result = await Navigator.of(context).push<CameraCaptureResult>(
                CupertinoPageRoute<CameraCaptureResult>(
                  builder: (_) => CameraCapturePage(
                    initialMode: MediaPickerEntryMode.image,
                    allowVideoMode: false,
                    previewBuilder: _fakePreview,
                    previewCameraDescriptions: _fakeBackAndFrontCameras,
                    filterRepository: _FakeFilterRepository(),
                    photoCapture: _fakeCapture,
                    imageEditorLauncher: _fakeEditorLauncher,
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open camera'));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.cameraUsePhoto));
    await tester.pumpAndSettle();

    expect(result?.path, '/tmp/edited.jpg');
    expect(result?.type, CreateMediaType.image);
    expect(result?.filterPresetId, 'original');
  });
}

Future<List<CameraDescription>> _noAvailableCameras() async => const [];

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

Future<String?> _fakeEditorLauncher(
  BuildContext context,
  CameraPhotoEditorRequest request,
) async {
  expect(request.path, '/tmp/captured.jpg');
  expect(request.caller, CameraPhotoCaller.picker);
  expect(request.entrySource, CameraPhotoEntrySource.photoPicker);
  return '/tmp/edited.jpg';
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
      ImageEditorFilterPreset(
        id: 'cool',
        categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
        name: UITextConstants.imageEditCameraCool,
        sort: 2,
        enabled: true,
        defaultStrength: 80,
        params: <String, double>{'temperature': -12},
      ),
    ];
  }
}
