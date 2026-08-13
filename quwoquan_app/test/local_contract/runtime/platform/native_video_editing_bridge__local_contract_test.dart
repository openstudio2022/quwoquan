// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#open-007
//
// 平台中立视频编辑桥合同：iOS 与 Android 共用 `quwoquan/video_editing`
// channel 契约（方法名/参数/响应逐字段一致）；不支持原生 channel 的平台
// 必须结构化降级，禁止伪成功。
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/native_video_editing_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(videoEditingMethodChannel, null);
  });

  test('exportEdit 参数透传与响应解析与 channel 契约逐字段一致', () async {
    MethodCall? received;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(videoEditingMethodChannel, (call) async {
          received = call;
          return <String, dynamic>{
            'videoPath': '/tmp/edited_video_1.mp4',
            'coverPath': '/tmp/video_cover_1.jpg',
            'durationMs': 5400,
          };
        });

    final service = NativeVideoEditingService(
      supportsNativeChannelOverride: true,
    );
    final result = await service.exportEdit(
      sourcePath: '/tmp/source.mp4',
      trimStartMs: 1200,
      trimEndMs: 6600,
      muted: true,
      coverTimeMs: 1500,
    );

    expect(received, isNotNull);
    expect(received!.method, 'exportVideoEdit');
    expect(received!.arguments, <String, dynamic>{
      'sourcePath': '/tmp/source.mp4',
      'trimStartMs': 1200,
      'trimEndMs': 6600,
      'muted': true,
      'coverTimeMs': 1500,
    });
    expect(result.videoPath, '/tmp/edited_video_1.mp4');
    expect(result.coverPath, '/tmp/video_cover_1.jpg');
    expect(result.durationMs, 5400);
  });

  test('extractFrames 透传帧提取请求并解析 [{path,timeMs}] 响应', () async {
    MethodCall? received;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(videoEditingMethodChannel, (call) async {
          received = call;
          return <dynamic>[
            <String, dynamic>{'path': '/tmp/frame_0.jpg', 'timeMs': 0},
            <String, dynamic>{'path': '/tmp/frame_1.jpg', 'timeMs': 900},
            <String, dynamic>{'path': '', 'timeMs': 1800},
          ];
        });

    final service = NativeVideoEditingService(
      supportsNativeChannelOverride: true,
    );
    final frames = await service.extractFrames(
      videoPath: '/tmp/source-frames.mp4',
      startMs: 0,
      endMs: 1800,
      frameCount: 2,
      maxDimension: 240,
    );

    expect(received!.method, 'extractVideoFrames');
    final arguments = Map<String, dynamic>.from(received!.arguments as Map);
    expect(arguments['sourcePath'], '/tmp/source-frames.mp4');
    expect(arguments['startMs'], 0);
    expect(arguments['endMs'], 1800);
    expect(arguments['maxDimension'], 240);
    // 空 path 的帧被过滤；采样到请求帧数。
    expect(frames, hasLength(2));
    expect(frames.first.path, '/tmp/frame_0.jpg');
    expect(frames.last.timeMs, 900);
  });

  test('原生导出失败（PlatformException）且需要真实编辑时结构化不可用', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(videoEditingMethodChannel, (call) async {
          throw PlatformException(
            code: 'video_editing_export_failed',
            message: 'transformer error',
          );
        });

    final service = NativeVideoEditingService(
      supportsNativeChannelOverride: true,
    );
    await expectLater(
      service.exportEdit(
        sourcePath: '/tmp/source.mp4',
        trimStartMs: 1000,
        trimEndMs: 2000,
        muted: false,
        coverTimeMs: 0,
      ),
      throwsUnsupportedError,
    );
  });

  test('非移动平台需要 trim/mute 时结构化不可用，不产生伪成功', () async {
    final service = NativeVideoEditingService(
      supportsNativeChannelOverride: false,
    );
    await expectLater(
      service.exportEdit(
        sourcePath: '/tmp/source.mp4',
        trimStartMs: 500,
        trimEndMs: 1500,
        muted: true,
        coverTimeMs: 0,
      ),
      throwsUnsupportedError,
    );
  });
}
