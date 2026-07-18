import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';

void main() {
  group('VideoPlaybackSession', () {
    test('用户暂停始终压过后续自动播放资格', () async {
      final session = VideoPlaybackSession();
      addTearDown(session.dispose);

      session.setAutomaticPlaybackEligible(true);
      await session.pauseByUser();
      session.setAutomaticPlaybackEligible(true);

      expect(session.snapshot.intent, VideoPlaybackIntent.manualPause);
      expect(
        session.snapshot.controlsVisibility,
        VideoPlaybackControlsVisibility.pinned,
      );
      expect(session.snapshot.pauseReason, VideoPlaybackPauseReason.user);
    });

    test('失去自动播放资格会经会话状态机暂停，而非由宿主直接控制播放器', () {
      final session = VideoPlaybackSession();
      addTearDown(session.dispose);

      session.setAutomaticPlaybackEligible(true);
      session.setAutomaticPlaybackEligible(false);

      expect(session.snapshot.intent, VideoPlaybackIntent.interrupted);
      expect(session.snapshot.pauseReason, VideoPlaybackPauseReason.focusLost);
    });

    test('用户手动播放不依赖自动播放资格', () async {
      final session = VideoPlaybackSession();
      addTearDown(session.dispose);

      await session.playByUser();

      expect(session.snapshot.intent, VideoPlaybackIntent.manualPlay);
      expect(
        session.snapshot.controlsVisibility,
        VideoPlaybackControlsVisibility.transient,
      );
    });

    test('媒体错误进入结构化 failure 状态并清空拖动目标', () {
      final session = VideoPlaybackSession();
      addTearDown(session.dispose);

      session.setVerifiedDuration(const Duration(seconds: 10));
      session.markFailure();

      expect(session.snapshot.transport, VideoPlaybackTransport.failure);
      expect(session.snapshot.pauseReason, VideoPlaybackPauseReason.failure);
      expect(session.snapshot.scrubTarget, isNull);
    });

    test('权威时长在原生时长不可用时可用于渲染，且 QoE 不伪造观测值', () {
      final session = VideoPlaybackSession();
      addTearDown(session.dispose);

      session.setVerifiedDuration(const Duration(seconds: 12));
      final qoe = session.takeQoeSummary();

      expect(session.snapshot.duration, const Duration(seconds: 12));
      expect(qoe.declaredDurationMs, 12000);
      expect(qoe.observedDurationMs, isNull);
      expect(qoe.durationMismatch, isNull);
    });
  });
}
