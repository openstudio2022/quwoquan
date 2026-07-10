import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

/// 共享高保相机壳，但图片与视频路由语义、返回结果类型、主按钮、标题必须互不串线。
void main() {
  testWidgets('图片路由：拍照模式标题 + 白色快门，返回 image 结果且不出现录像按钮', (tester) async {
    CameraCaptureResult? result;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open photo'),
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

    await tester.tap(find.text('open photo'));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.cameraPhotoModeTitle), findsOneWidget);
    expect(find.text(UITextConstants.cameraVideoModeTitle), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsNothing,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-capture-action')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.cameraUsePhoto));
    await tester.pumpAndSettle();

    expect(result?.type, CreateMediaType.image);
    expect(result?.type, isNot(CreateMediaType.video));
    expect(result?.path, '/tmp/edited.jpg');
  });

  testWidgets('视频路由：摄像模式标题 + 蓝色录像按钮，返回 video 结果且不出现白色快门', (tester) async {
    CameraCaptureResult? result;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open video'),
            onPressed: () async {
              result = await Navigator.of(context).push<CameraCaptureResult>(
                CupertinoPageRoute<CameraCaptureResult>(
                  builder: (_) => CameraCapturePage(
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
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('open video'));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.cameraVideoModeTitle), findsOneWidget);
    expect(find.text(UITextConstants.cameraPhotoModeTitle), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsNothing,
    );

    await tester.tap(find.byKey(const ValueKey<String>('camera-record-action')));
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 400));
    }
    await tester.tap(find.byKey(const ValueKey<String>('camera-record-action')));
    await tester.pump();
    await tester.pumpAndSettle();
    // 视频先进预览确认（重拍/下一步），不会落到图片确认文案。
    expect(find.text(UITextConstants.cameraVideoNext), findsOneWidget);
    expect(find.text(UITextConstants.cameraUsePhoto), findsNothing);

    await tester.tap(find.byKey(const ValueKey<String>('camera-use-video-action')));
    await tester.pumpAndSettle();

    expect(result?.type, CreateMediaType.video);
    expect(result?.type, isNot(CreateMediaType.image));
    expect(result?.path, '/tmp/recorded.mp4');
  });
}

Future<bool> _grantedMicrophone() async => true;

Future<void> _fakeRecordingStart() async {}

Future<String> _fakeRecordingStop() async => '/tmp/recorded.mp4';

Future<String> _fakeCapture() async => '/tmp/captured.jpg';

Future<String?> _fakeEditorLauncher(
  BuildContext context,
  CameraPhotoEditorRequest request,
) async {
  return '/tmp/edited.jpg';
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
        name: UITextConstants.imageEditOriginal,
        sort: 1,
        enabled: true,
        defaultStrength: 0,
        params: <String, double>{},
      ),
    ];
  }
}
