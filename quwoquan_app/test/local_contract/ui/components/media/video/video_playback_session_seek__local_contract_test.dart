import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/video_playback_session.dart';
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

  test('release seek command 永不返回时在统一 deadline 内进入 typed timeout', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession(
      seekCommandTimeout: const Duration(milliseconds: 10),
    )..attach(controller);
    final stalledSeek = Completer<void>();
    fakePlatform.seekCompleter = stalledSeek;

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 62));
    await session.endScrub().timeout(const Duration(milliseconds: 250));

    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandTimedOut,
    );
    expect(
      session.snapshot.runtimeFailure?.semanticReason,
      'seek_command_timeout',
    );
    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 1);
    expect(summary.seekFailureCount, 1);
    expect(summary.seekCommandMaxMs, greaterThanOrEqualTo(1));
    expect(summary.seekSettleMaxMs, 0);

    fakePlatform.seekCompleter = null;
    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 24));
    await session.endScrub().timeout(const Duration(milliseconds: 250));
    expect(
      session.snapshot.lastSeekLifecycleEvent,
      isA<VideoSeekLifecycleEvent>()
          .having(
            (event) => event.phase,
            'phase',
            VideoSeekLifecyclePhase.commandCompleted,
          )
          .having(
            (event) => event.target,
            'target',
            const Duration(seconds: 24),
          ),
    );
    expect(session.snapshot.runtimeFailure, isNull);

    stalledSeek.complete();
    await _flushAsync();
    expect(
      session.snapshot.lastSeekLifecycleEvent?.target,
      const Duration(seconds: 24),
    );
    final recoveredSummary = session.takeQoeSummary();
    expect(recoveredSummary.seekCount, 2);
    expect(recoveredSummary.seekFailureCount, 1);

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('release seek command 永不返回时 detach 立即以 superseded 唤醒', () async {
    final controller = await _initializedController();
    final observedPhases = <VideoSeekLifecyclePhase>[];
    final session = VideoPlaybackSession(
      seekCommandTimeout: const Duration(seconds: 1),
    )..attach(controller);
    session.addListener(() {
      final phase = session.snapshot.lastSeekLifecycleEvent?.phase;
      if (phase != null) {
        observedPhases.add(phase);
      }
    });
    fakePlatform.seekCompleter = Completer<void>();

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 62));
    final releaseSeek = session.endScrub();
    await _flushAsync();
    session.detach(controller);
    await releaseSeek.timeout(const Duration(milliseconds: 250));

    expect(observedPhases, contains(VideoSeekLifecyclePhase.superseded));
    expect(session.takeQoeSummary().seekFailureCount, 0);

    session.dispose();
    await controller.dispose();
  });

  test('普通与 source-switch seek 共用每 controller 两个物理未决命令硬上限', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession(
      seekCommandTimeout: const Duration(milliseconds: 10),
    )..attach(controller, synchronizeAutomaticPlayback: false);
    final firstStalledSeek = Completer<void>();
    fakePlatform.seekCompleter = firstStalledSeek;

    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 12));
    await session.endScrub().timeout(const Duration(milliseconds: 250));
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandTimedOut,
    );

    final secondStalledSeek = Completer<void>();
    fakePlatform.seekCompleter = secondStalledSeek;
    final sourceTimeout = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 24),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
          settleTimeout: const Duration(milliseconds: 10),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(sourceTimeout.outcome, VideoSourceSwitchSeekOutcome.commandTimedOut);
    expect(fakePlatform.seekTargets, hasLength(2));

    controller.value = controller.value.copyWith(
      position: controller.value.duration,
      isPlaying: false,
    );
    await session.playByUser().timeout(const Duration(milliseconds: 250));
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandCapacityExceeded,
    );
    expect(fakePlatform.seekTargets, hasLength(2));

    fakePlatform.seekCompleter = Completer<void>();
    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 36));
    await session.endScrub().timeout(const Duration(milliseconds: 250));
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandCapacityExceeded,
    );
    expect(
      session.snapshot.runtimeFailure?.semanticReason,
      'seek_command_capacity_exceeded',
    );
    expect(fakePlatform.seekTargets, hasLength(2));

    final sourceRejected = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 48),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
          settleTimeout: const Duration(milliseconds: 100),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(
      sourceRejected.outcome,
      VideoSourceSwitchSeekOutcome.commandCapacityExceeded,
    );
    expect(
      session.snapshot.runtimeFailure?.semanticReason,
      'source_switch_seek_command_capacity_exceeded',
    );
    expect(fakePlatform.seekTargets, hasLength(2));

    firstStalledSeek.complete();
    await _flushAsync();
    fakePlatform.seekCompleter = null;
    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 60));
    await session.endScrub().timeout(const Duration(milliseconds: 250));
    expect(fakePlatform.seekTargets, hasLength(3));
    expect(
      session.snapshot.lastSeekLifecycleEvent,
      isA<VideoSeekLifecycleEvent>()
          .having(
            (event) => event.phase,
            'phase',
            VideoSeekLifecyclePhase.commandCompleted,
          )
          .having(
            (event) => event.target,
            'target',
            const Duration(seconds: 60),
          ),
    );

    secondStalledSeek.complete();
    await _flushAsync();
    expect(
      session.snapshot.lastSeekLifecycleEvent?.target,
      const Duration(seconds: 60),
    );
    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 6);
    expect(summary.seekFailureCount, 5);
    expect(summary.seekEvidenceSource, 'controller_command_completion');

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('跨 controller epoch 的永不完成 seek 仍受 session-global 物理硬上限', () async {
    final firstController = await _initializedController();
    final secondController = await _initializedController();
    final thirdController = await _initializedController();
    final fourthController = await _initializedController();
    final session = VideoPlaybackSession();

    final firstStalledSeek = Completer<void>();
    session.attach(firstController, synchronizeAutomaticPlayback: false);
    fakePlatform.seekCompleter = firstStalledSeek;
    final firstResult = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 12),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
          settleTimeout: const Duration(milliseconds: 10),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(firstResult.outcome, VideoSourceSwitchSeekOutcome.commandTimedOut);
    expect(session.debugUnresolvedPhysicalSeekCommandCount, 1);
    expect(session.debugUnresolvedPhysicalSeekControllerCount, 1);
    session.detach(firstController);

    final secondStalledSeek = Completer<void>();
    session.attach(secondController, synchronizeAutomaticPlayback: false);
    fakePlatform.seekCompleter = secondStalledSeek;
    final secondResult = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 24),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
          settleTimeout: const Duration(milliseconds: 10),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(secondResult.outcome, VideoSourceSwitchSeekOutcome.commandTimedOut);
    session.detach(secondController);
    expect(fakePlatform.seekTargets, hasLength(2));
    expect(session.debugUnresolvedPhysicalSeekCommandCount, 2);
    expect(session.debugUnresolvedPhysicalSeekControllerCount, 2);

    session.attach(thirdController, synchronizeAutomaticPlayback: false);
    fakePlatform.seekCompleter = Completer<void>();
    final thirdResult = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 36),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
        )
        .timeout(const Duration(milliseconds: 250));
    expect(
      thirdResult.outcome,
      VideoSourceSwitchSeekOutcome.commandCapacityExceeded,
    );
    session.detach(thirdController);

    session.attach(fourthController, synchronizeAutomaticPlayback: false);
    final fourthResult = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 48),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
        )
        .timeout(const Duration(milliseconds: 250));
    expect(
      fourthResult.outcome,
      VideoSourceSwitchSeekOutcome.commandCapacityExceeded,
    );
    expect(
      fakePlatform.seekTargets,
      hasLength(2),
      reason: '换 controller/epoch 不得绕过 session-global 未决物理命令硬上限',
    );
    expect(session.debugUnresolvedPhysicalSeekCommandCount, 2);
    expect(session.debugUnresolvedPhysicalSeekControllerCount, 2);

    firstStalledSeek.complete();
    await _flushAsync();
    fakePlatform.seekCompleter = null;
    final recovered = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 60),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.positionReadbackOnly,
          settleTimeout: const Duration(milliseconds: 100),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(
      recovered.outcome,
      VideoSourceSwitchSeekOutcome.positionReadbackSettled,
    );
    expect(fakePlatform.seekTargets, hasLength(3));
    expect(session.debugUnresolvedPhysicalSeekCommandCount, 1);
    expect(session.debugUnresolvedPhysicalSeekControllerCount, 1);

    secondStalledSeek.complete();
    await _flushAsync();
    expect(session.snapshot.lastSourceSwitchSeekResult, same(recovered));
    expect(session.debugUnresolvedPhysicalSeekCommandCount, 0);
    expect(session.debugUnresolvedPhysicalSeekControllerCount, 0);

    session
      ..detach(fourthController)
      ..dispose();
    await firstController.dispose();
    await secondController.dispose();
    await thirdController.dispose();
    await fourthController.dispose();
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

    await releaseSeek.timeout(const Duration(milliseconds: 250));

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

  test('source switch 在 attach 后只以原生渲染帧结算 native settle', () async {
    final controller = await _initializedController();
    final signals = StreamController<VideoNativePlaybackSignal>.broadcast();
    final session = VideoPlaybackSession()
      ..attach(
        controller,
        nativeSignals: signals.stream,
        synchronizeAutomaticPlayback: false,
      );

    final restore = session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
      settleTimeout: const Duration(milliseconds: 100),
    );
    await _flushAsync();
    signals.add(
      const VideoNativePlaybackSignal(
        kind: VideoNativePlaybackSignalKind.seekSettled,
        targetPositionMs: 37000,
        settledPositionMs: 36500,
        settleMs: 84,
      ),
    );

    final result = await restore;
    expect(result.outcome, VideoSourceSwitchSeekOutcome.nativeSettled);
    expect(result.observedPosition, const Duration(milliseconds: 36500));
    expect(session.snapshot.lastSourceSwitchSeekResult, same(result));
    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 1);
    expect(summary.seekFailureCount, 0);
    expect(summary.seekSettleMaxMs, 84);
    expect(summary.seekEvidenceSource, 'source_switch_native_settled');

    await signals.close();
    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('source switch 原生 settle 超时进入 typed QoE 失败而不伪造帧证据', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);

    final result = await session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
      settleTimeout: const Duration(milliseconds: 5),
    );

    expect(result.outcome, VideoSourceSwitchSeekOutcome.nativeSettleTimedOut);
    expect(result.isSettled, isFalse);
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.settleTimedOut,
    );
    final summary = session.takeQoeSummary();
    expect(summary.seekFailureCount, 1);
    expect(summary.seekEvidenceSource, 'source_switch_native_settle_timeout');

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('source switch seek command 永不返回时共用 settle deadline 收口', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);
    final stalledSeek = Completer<void>();
    fakePlatform.seekCompleter = stalledSeek;

    final result = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 37),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
          settleTimeout: const Duration(milliseconds: 10),
        )
        .timeout(const Duration(milliseconds: 250));

    expect(result.outcome, VideoSourceSwitchSeekOutcome.commandTimedOut);
    expect(result.isSettled, isFalse);
    expect(
      session.snapshot.lastSeekLifecycleEvent?.phase,
      VideoSeekLifecyclePhase.commandTimedOut,
    );
    expect(
      session.snapshot.runtimeFailure?.semanticReason,
      'source_switch_seek_command_timeout',
    );
    final summary = session.takeQoeSummary();
    expect(summary.seekFailureCount, 1);
    expect(summary.seekCommandMaxMs, greaterThanOrEqualTo(1));
    expect(summary.seekSettleMaxMs, 0);
    expect(summary.seekEvidenceSource, 'source_switch_command_failed');

    fakePlatform.seekCompleter = null;
    final recovered = await session
        .restoreSourceSwitchPosition(
          const Duration(seconds: 48),
          evidenceCapability:
              VideoSeekSettleEvidenceCapability.positionReadbackOnly,
          settleTimeout: const Duration(milliseconds: 100),
        )
        .timeout(const Duration(milliseconds: 250));
    expect(
      recovered.outcome,
      VideoSourceSwitchSeekOutcome.positionReadbackSettled,
    );
    expect(recovered.target, const Duration(seconds: 48));

    stalledSeek.complete();
    await _flushAsync();
    expect(session.snapshot.lastSourceSwitchSeekResult, same(recovered));
    final recoveredSummary = session.takeQoeSummary();
    expect(recoveredSummary.seekCount, 2);
    expect(recoveredSummary.seekFailureCount, 1);

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('source switch 非原生平台只接纳 position readback 并标记 unsupported 边界', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);

    final result = await session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability:
          VideoSeekSettleEvidenceCapability.positionReadbackOnly,
    );

    expect(
      result.outcome,
      VideoSourceSwitchSeekOutcome.positionReadbackSettled,
    );
    expect(result.isSettled, isTrue);
    expect(result.observedPosition, const Duration(seconds: 37));
    expect(
      result.evidenceCapability,
      VideoSeekSettleEvidenceCapability.positionReadbackOnly,
    );
    expect(
      session.takeQoeSummary().seekEvidenceSource,
      'source_switch_position_readback_native_unsupported',
    );

    session
      ..detach(controller)
      ..dispose();
    await controller.dispose();
  });

  test('source switch readback 不可用与 seek 命令失败均为可区分终态', () async {
    final readbackController = await _initializedController();
    final readbackSession = VideoPlaybackSession()
      ..attach(readbackController, synchronizeAutomaticPlayback: false);
    fakePlatform.failNextPositionReadback = true;

    final unsupported = await readbackSession.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability:
          VideoSeekSettleEvidenceCapability.positionReadbackOnly,
    );
    expect(unsupported.outcome, VideoSourceSwitchSeekOutcome.settleUnsupported);
    expect(
      readbackSession.takeQoeSummary().seekEvidenceSource,
      'source_switch_settle_unsupported',
    );
    readbackSession.detach(readbackController);
    await readbackController.dispose();

    final failedController = await _initializedController();
    final failedSession = VideoPlaybackSession()
      ..attach(failedController, synchronizeAutomaticPlayback: false);
    fakePlatform.failNextSeek = true;
    final failed = await failedSession.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability:
          VideoSeekSettleEvidenceCapability.positionReadbackOnly,
    );
    expect(failed.outcome, VideoSourceSwitchSeekOutcome.commandFailed);
    expect(failedSession.snapshot.runtimeFailure, isNotNull);
    final failedSummary = failedSession.takeQoeSummary();
    expect(failedSummary.seekFailureCount, 1);
    expect(failedSummary.seekEvidenceSource, 'source_switch_command_failed');

    readbackSession.dispose();
    failedSession
      ..detach(failedController)
      ..dispose();
    await failedController.dispose();
  });

  test('source switch 旧 controller epoch 被 detach 后只返回 superseded', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);
    final seekCompletion = Completer<void>();
    fakePlatform.seekCompleter = seekCompletion;

    final restore = session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
    );
    await _flushAsync();
    session.detach(controller);

    final result = await restore.timeout(const Duration(milliseconds: 250));
    expect(result.outcome, VideoSourceSwitchSeekOutcome.superseded);
    expect(result.countsAsFailure, isFalse);
    expect(fakePlatform.seekTargets, <Duration>[const Duration(seconds: 37)]);

    session.dispose();
    await controller.dispose();
  });

  test('source switch 永不返回的 command 在 attach 替代 epoch 时立即结束', () async {
    final controller = await _initializedController();
    final replacement = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);
    final stalledSeek = Completer<void>();
    fakePlatform.seekCompleter = stalledSeek;

    final restore = session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
    );
    await _flushAsync();
    session.attach(replacement, synchronizeAutomaticPlayback: false);

    final result = await restore.timeout(const Duration(milliseconds: 250));
    expect(result.outcome, VideoSourceSwitchSeekOutcome.superseded);
    expect(result.countsAsFailure, isFalse);

    stalledSeek.complete();
    await _flushAsync();
    session
      ..detach(replacement)
      ..dispose();
    await controller.dispose();
    await replacement.dispose();
  });

  test('source switch 永不返回的 command 在 session dispose 时立即结束', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);
    final stalledSeek = Completer<void>();
    fakePlatform.seekCompleter = stalledSeek;

    final restore = session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
    );
    await _flushAsync();
    session.dispose();

    final result = await restore.timeout(const Duration(milliseconds: 250));
    expect(result.outcome, VideoSourceSwitchSeekOutcome.superseded);
    expect(result.countsAsFailure, isFalse);

    stalledSeek.complete();
    await _flushAsync();
    await controller.dispose();
  });

  test('source switch 未决 seek 在 QoE 快照前以 superseded 收口', () async {
    final controller = await _initializedController();
    final session = VideoPlaybackSession()
      ..attach(controller, synchronizeAutomaticPlayback: false);
    final seekCompletion = Completer<void>();
    fakePlatform.seekCompleter = seekCompletion;

    final restore = session.restoreSourceSwitchPosition(
      const Duration(seconds: 37),
      evidenceCapability: VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
    );
    await _flushAsync();

    final summary = session.takeQoeSummary();
    expect(summary.seekCount, 1);
    expect(summary.seekFailureCount, 0);
    expect(summary.seekEvidenceSource, 'source_switch_superseded');

    final result = await restore.timeout(const Duration(milliseconds: 250));
    expect(result.outcome, VideoSourceSwitchSeekOutcome.superseded);
    expect(
      session.snapshot.lastSourceSwitchSeekResult?.outcome,
      VideoSourceSwitchSeekOutcome.superseded,
    );

    session.detach(controller);
    expect(session.snapshot.lastSourceSwitchSeekResult, isNull);
    session.dispose();
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
