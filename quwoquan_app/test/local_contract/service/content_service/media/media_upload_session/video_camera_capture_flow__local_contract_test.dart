import 'package:camera/camera.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_repository.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';

void main() {
  testWidgets('视频摄像模式标题与默认后置摄像头，蓝色录像按钮替代白色快门', (tester) async {
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

    expect(find.text(MediaText.cameraVideoModeTitle), findsOneWidget);
    expect(find.text(MediaText.cameraPhotoModeTitle), findsNothing);
    // 视频专用蓝色录像按钮，不出现白色快门。
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-capture-action')),
      findsNothing,
    );
    // 默认后置摄像头 -> 灯光可用（前置时会置灰）。
    final lightButton = tester.widget<CupertinoButton>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('camera-light-action')),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(lightButton.onPressed, isNotNull);
  });

  testWidgets('视频相机不可用时复用深色错误语义且隐藏无意义控件', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        theme: const CupertinoThemeData(brightness: Brightness.light),
        home: CameraCapturePage(
          initialMode: MediaPickerEntryMode.video,
          allowVideoMode: true,
          cameraDiscovery: _noAvailableCameras,
          filterRepository: _FakeFilterRepository(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
    expect(find.text(SearchText.recoveryReloadLaterMessage), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('camera-rotate-action')),
      findsNothing,
    );
    final titleFinder = find.text(SearchText.recoveryReloadLaterTitle);
    final titleContext = tester.element(titleFinder);
    expect(MediaQuery.of(titleContext).platformBrightness, Brightness.dark);
    expect(CupertinoTheme.of(titleContext).brightness, Brightness.dark);
  });

  testWidgets('录制后进入视频预览确认并返回视频拍摄结果', (tester) async {
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

    await tester.tap(find.text('open camera'));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    // 推进录制时长越过最短限制（默认 1s）。
    for (var i = 0; i < 4; i++) {
      await tester.pump(const Duration(milliseconds: 400));
    }
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    await tester.pump();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraVideoRetake), findsOneWidget);
    expect(find.text(MediaText.cameraVideoNext), findsOneWidget);
    final retakeContainer = tester.widget<Container>(
      find
          .descendant(
            of: find.byKey(
              const ValueKey<String>('camera-retake-video-action'),
            ),
            matching: find.byWidgetPredicate(
              (widget) =>
                  widget is Container && widget.decoration is BoxDecoration,
            ),
          )
          .first,
    );
    final retakeDecoration = retakeContainer.decoration! as BoxDecoration;
    expect(retakeDecoration.border, isNotNull);
    expect(
      ((retakeDecoration.color?.r ?? 0) * 255.0).round().clamp(0, 255),
      greaterThan(0),
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-use-video-action')),
    );
    await tester.pumpAndSettle();

    expect(result?.path, '/tmp/recorded.mp4');
    expect(result?.type, CreateMediaType.video);
  });

  testWidgets('录制中锁定滤镜与翻转', (tester) async {
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
          minRecordingMs: 0,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    final filterButton = tester.widget<CupertinoButton>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('camera-filter-action')),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(filterButton.onPressed, isNull);
    final rotateButton = tester.widget<CupertinoButton>(
      find.descendant(
        of: find.byKey(const ValueKey<String>('camera-rotate-action')),
        matching: find.byType(CupertinoButton),
      ),
    );
    expect(rotateButton.onPressed, isNull);

    // 停止录制以取消计时器，避免残存 Timer。
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text(MediaText.cameraVideoNext), findsOneWidget);
  });

  testWidgets('录制过短提示且不进入预览确认', (tester) async {
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

    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    await tester.tap(
      find.byKey(const ValueKey<String>('camera-record-action')),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraVideoRecordTooShort), findsOneWidget);
    expect(find.text(MediaText.cameraVideoNext), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('camera-record-action')),
      findsOneWidget,
    );

    // 排空 Toast 的自动消失计时器，避免残存 Timer。
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('录后预览加载失败时不再无限转圈而是展示明确失败占位', (tester) async {
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
          videoRecordingStop: _invalidRecordingStop,
          videoFileReadyProbe: _alwaysUnreadyVideo,
        ),
      ),
    );
    await tester.pumpAndSettle();

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
    await tester.pumpAndSettle();

    expect(find.text(MediaText.cameraVideoPreviewUnavailable), findsOneWidget);
    expect(
      find.text(MediaText.cameraVideoPreviewUnavailableHint),
      findsOneWidget,
    );
    final retakeDecoration = _buttonDecoration(
      tester,
      const ValueKey<String>('camera-retake-video-action'),
    );
    final nextDecoration = _buttonDecoration(
      tester,
      const ValueKey<String>('camera-use-video-action'),
    );
    expect(
      (retakeDecoration.color?.a ?? 0),
      greaterThan(nextDecoration.color?.a ?? 0),
    );
    expect(nextDecoration.color, isNot(AppColors.primaryColor));
  });

  testWidgets('录后返回放弃弹窗使用品牌蓝放弃动作且不再展示 destructive 红色图标', (tester) async {
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
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey<String>('camera-back-action')));
    await tester.pumpAndSettle();

    expect(find.byIcon(CupertinoIcons.delete), findsNothing);
    final discardText = tester.widget<Text>(
      find.text(MediaText.cameraVideoDiscardConfirm),
    );
    final textContext = tester.element(
      find.text(MediaText.cameraVideoDiscardConfirm),
    );
    expect(discardText.style?.color, AppColors.iosAccent(textContext));
  });
}

BoxDecoration _buttonDecoration(WidgetTester tester, Key key) {
  final container = tester.widget<Container>(
    find
        .descendant(
          of: find.byKey(key),
          matching: find.byWidgetPredicate(
            (widget) =>
                widget is Container && widget.decoration is BoxDecoration,
          ),
        )
        .first,
  );
  return container.decoration! as BoxDecoration;
}

Future<List<CameraDescription>> _noAvailableCameras() async => const [];

Future<bool> _grantedMicrophone() async => true;

Future<void> _fakeRecordingStart() async {}

Future<String> _fakeRecordingStop() async => '/tmp/recorded.mp4';

Future<String> _invalidRecordingStop() async => '/tmp/missing-recorded.mp4';

Future<bool> _alwaysUnreadyVideo(String path) async => false;

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
  return ColoredBox(
    key: const ValueKey<String>('fake-video-preview'),
    color: CupertinoColors.black,
  );
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
