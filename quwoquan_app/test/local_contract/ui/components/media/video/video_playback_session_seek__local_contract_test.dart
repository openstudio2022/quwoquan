import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/video/fake_video_player_platform.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late VideoPlayerPlatform originalPlatform;
  late FakeVideoPlayerPlatform fakePlatform;

  setUp(() {
    originalPlatform = VideoPlayerPlatform.instance;
    fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
  });

  tearDown(() {
    VideoPlayerPlatform.instance = originalPlatform;
  });

  test('拖动仅在释放时提交一次 seek，并在原本播放时恢复', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..setAutomaticPlaybackEligible(true)
      ..attach(controller);
    await _flushAsync();
    final playCountBeforeScrub = fakePlatform.playCount;

    await session.beginScrub();
    session
      ..updateScrubTarget(const Duration(seconds: 10))
      ..updateScrubTarget(const Duration(seconds: 75))
      ..updateScrubTarget(const Duration(minutes: 2));
    expect(fakePlatform.seekTargets, isEmpty);
    expect(session.snapshot.isScrubbing, isTrue);
    expect(session.snapshot.scrubTarget, const Duration(minutes: 2));

    await session.endScrub();

    expect(fakePlatform.seekTargets, <Duration>[const Duration(minutes: 2)]);
    expect(fakePlatform.playCount, playCountBeforeScrub + 1);
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandCompleted,
    );
    expect(session.snapshot.runtimeFailure, isNull);

    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 1);
    expect(summary.seekFailureCount, 0);
    expect(summary.seekCommandMaxMs, greaterThanOrEqualTo(0));
    expect(summary.seekEvidenceSource, 'controller_command_completion');

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('QoE 汇总只累计前台可见且非缓冲的真实播放时长', () async {
    var now = DateTime.utc(2026, 7, 20, 12);
    final controller = await _initializedController();
    controller.value = controller.value.copyWith(isPlaying: true);
    final session = VideoPlaybackSession(now: () => now)
      ..setAutomaticPlaybackEligible(true)
      ..attach(controller);

    now = now.add(const Duration(milliseconds: 1800));
    controller.value = controller.value.copyWith(isBuffering: true);
    now = now.add(const Duration(milliseconds: 700));
    controller.value = controller.value.copyWith(isBuffering: false);
    now = now.add(const Duration(milliseconds: 1200));

    expect(session.takeQoeSummary().effectivePlaybackMs, 3000);

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('取消拖动回滚位置且不提交 seek', () async {
    final controller = await _initializedController();
    controller.value = controller.value.copyWith(
      position: const Duration(seconds: 10),
      isPlaying: false,
    );
    final session = VideoPlaybackSession()..attach(controller);

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 90));
    await session.endScrub(commit: false);
    await _flushAsync();

    expect(fakePlatform.seekTargets, isEmpty);
    expect(session.snapshot.isScrubbing, isFalse);
    expect(session.snapshot.position, const Duration(seconds: 10));

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('seek 失败进入结构化失败并进入 QoE 失败计数', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()..attach(controller);
    fakePlatform.failNextSeek = true;

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 62));
    await session.endScrub();

    expect(
      session.snapshot.runtimeFailure?.code,
      'CONTENT.SYSTEM.media_seek_failed',
    );
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.failed,
    );
    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 1);
    expect(summary.seekFailureCount, 1);

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('buffering 冻结最后稳定位置，结束态可从零重播', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()..attach(controller);
    controller.value = controller.value.copyWith(
      position: const Duration(seconds: 35),
      isBuffering: false,
    );
    expect(session.snapshot.position, const Duration(seconds: 35));

    controller.value = controller.value.copyWith(
      position: const Duration(seconds: 50),
      isBuffering: true,
    );
    expect(session.snapshot.position, const Duration(seconds: 35));

    controller.value = controller.value.copyWith(
      position: controller.value.duration,
      isBuffering: false,
      isPlaying: false,
    );
    expect(session.snapshot.isEnded, isTrue);
    await session.playByUser();

    expect(fakePlatform.seekTargets.last, Duration.zero);
    expect(fakePlatform.playCount, greaterThanOrEqualTo(1));

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('原生 seek settle 才能把证据源提升为 native_settled', () async {
    var now = DateTime.utc(2026, 7, 19, 12);
    final controller = await _initializedController();
    final signals = StreamController<VideoNativePlaybackSignal>.broadcast();
    final session = VideoPlaybackSession(now: () => now)
      ..attach(controller, nativeSignals: signals.stream);

    signals.add(
      VideoNativePlaybackSignal(
        kind: VideoNativePlaybackSignalKind.renderedFirstFrame,
        ttffMs: 380,
      ),
    );
    await _flushAsync();
    expect(session.takeQoeSummary().ttffMs, isNotNull);

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 42));
    now = now.add(const Duration(milliseconds: 40));
    await session.endScrub();
    expect(
      session.takeQoeSummary().seekEvidenceSource,
      'controller_command_completion',
    );

    now = now.add(const Duration(milliseconds: 90));
    signals.add(
      VideoNativePlaybackSignal(
        kind: VideoNativePlaybackSignalKind.seekSettled,
        targetPositionMs: 42000,
        settledPositionMs: 42000,
        settleMs: 130,
      ),
    );
    await _flushAsync();

    final summary = session.takeQoeSummary();
    expect(summary.seekEvidenceSource, 'native_settled');
    expect(summary.seekSettleMaxMs, 130);
    expect(
      session.snapshot.lastSeekLifecycleEvent?.hasNativeSettleEvidence,
      isTrue,
    );

    await signals.close();
    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('原生 settle 先于 seek 命令返回时仍保留原生证据', () async {
    final controller = await _initializedController();
    final signals = StreamController<VideoNativePlaybackSignal>.broadcast();
    final session = VideoPlaybackSession()
      ..setAutomaticPlaybackEligible(true)
      ..attach(controller, nativeSignals: signals.stream);
    final seekCompletion = Completer<void>();
    fakePlatform.seekCompleter = seekCompletion;
    controller.value = controller.value.copyWith(isPlaying: true);

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 42));
    final playCountBeforeRelease = fakePlatform.playCount;
    final releaseSeek = session.endScrub();
    await _flushAsync();

    signals.add(
      const VideoNativePlaybackSignal(
        kind: VideoNativePlaybackSignalKind.seekSettled,
        targetPositionMs: 42000,
        settledPositionMs: 42000,
        settleMs: 130,
      ),
    );
    await _flushAsync();
    expect(session.hasNativeSeekSettleEvidence, isTrue);

    seekCompletion.complete();
    await releaseSeek;

    final summary = session.takeQoeSummary();
    expect(fakePlatform.playCount, playCountBeforeRelease + 1);
    expect(summary.seekEvidenceSource, 'native_settled');
    expect(summary.seekSettleMaxMs, 130);
    expect(
      session.snapshot.lastSeekLifecycleEvent?.hasNativeSettleEvidence,
      isTrue,
    );

    await signals.close();
    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('原生诊断计数只在能力事件存在时进入 QoE', () async {
    final controller = await _initializedController();
    final signals = StreamController<VideoNativePlaybackSignal>.broadcast();
    final session = VideoPlaybackSession()
      ..attach(controller, nativeSignals: signals.stream);

    expect(session.takeQoeSummary().droppedFrames, isNull);
    expect(session.takeQoeSummary().audioUnderrunCount, isNull);

    signals
      ..add(
        const VideoNativePlaybackSignal(
          kind: VideoNativePlaybackSignalKind.playbackDiagnostics,
          rendererMode: 'platform_view',
          decoderQueueMode: 'synchronous',
          decoderFallbackEnabled: true,
        ),
      )
      ..add(
        const VideoNativePlaybackSignal(
          kind: VideoNativePlaybackSignalKind.videoFrameProcessing,
          processedFrames: 300,
        ),
      )
      ..add(
        const VideoNativePlaybackSignal(
          kind: VideoNativePlaybackSignalKind.droppedVideoFrames,
          droppedFrames: 2,
        ),
      )
      ..add(
        const VideoNativePlaybackSignal(
          kind: VideoNativePlaybackSignalKind.audioUnderrun,
        ),
      );
    await _flushAsync();

    final summary = session.takeQoeSummary();
    expect(summary.droppedFrames, 2);
    expect(summary.processedVideoFrames, 300);
    expect(summary.audioUnderrunCount, 1);
    expect(summary.rendererMode, 'platform_view');
    expect(summary.decoderQueueMode, 'synchronous');
    expect(summary.decoderFallbackEnabled, isTrue);

    await signals.close();
    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('原生诊断 observer 失败不阻断播放状态收敛', () async {
    final controller = await _initializedController();
    final signals = StreamController<VideoNativePlaybackSignal>.broadcast();
    final session = VideoPlaybackSession(
      onNativeSignal: (_) => throw StateError('diagnostic sink unavailable'),
    )..attach(controller, nativeSignals: signals.stream);

    signals.add(
      const VideoNativePlaybackSignal(
        kind: VideoNativePlaybackSignalKind.renderedFirstFrame,
        ttffMs: 240,
      ),
    );
    await _flushAsync();

    expect(session.takeQoeSummary().ttffMs, 240);

    await signals.close();
    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('有效播放只累计前台可见实际播放，排除拖动与后台时间', () async {
    var now = DateTime.utc(2026, 7, 19);
    final controller = await _initializedController();
    final session = VideoPlaybackSession(now: () => now)..attach(controller);
    controller.value = controller.value.copyWith(isPlaying: true);

    now = now.add(const Duration(seconds: 6));
    await session.beginScrub();
    now = now.add(const Duration(seconds: 20));
    await session.endScrub(commit: false);

    controller.value = controller.value.copyWith(isPlaying: true);
    now = now.add(const Duration(seconds: 2));
    session.setForeground(false);
    now = now.add(const Duration(seconds: 10));

    final evidence = session.takeEffectivePlaybackEvidence();
    expect(evidence.qualifies, isTrue);
    expect(evidence.effectivePlayMs, 8000);
    expect(evidence.totalUnits, 125);
    expect(evidence.playbackSessionId, isNotEmpty);

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });
}

Future<VideoPlayerController> _initializedController() async {
  final controller = VideoPlayerController.networkUrl(
    Uri.parse('https://media.example.test/video.mp4'),
  );
  await controller.initialize();
  return controller;
}

Future<void> _flushAsync() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}
