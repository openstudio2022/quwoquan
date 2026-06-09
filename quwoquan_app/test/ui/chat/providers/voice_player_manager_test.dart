import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:just_audio/just_audio.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_player_manager.dart';

void main() {
  group('VoicePlayerManager', () {
    test('空 URL 标记不可播放并记录失败事件', () async {
      final analytics = _FakeAnalyticsService();
      final backend = _FakeVoicePlaybackBackend();
      final container = ProviderContainer(
        overrides: [
          voicePlaybackBackendProvider.overrideWithValue(backend),
          voicePlaybackSourceResolverProvider.overrideWithValue(
            _fakeSourceResolver,
          ),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);

      await container
          .read(voicePlayerManagerProvider.notifier)
          .play('msg_1', '');

      final state = container.read(voicePlayerManagerProvider);
      expect(state.failedMessageId, 'msg_1');
      expect(state.error, UITextConstants.chatVoicePlayUnavailable);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_playback_failed'),
      );
    });

    test('切换语音会停止旧播放并设置新 source', () async {
      final backend = _FakeVoicePlaybackBackend();
      final container = ProviderContainer(
        overrides: [
          voicePlaybackBackendProvider.overrideWithValue(backend),
          voicePlaybackSourceResolverProvider.overrideWithValue(
            _fakeSourceResolver,
          ),
          analyticsProvider.overrideWithValue(_FakeAnalyticsService()),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(voicePlayerManagerProvider.notifier);
      await notifier.play('msg_1', 'https://cdn.example.com/a.m4a');
      await notifier.play('msg_2', 'https://cdn.example.com/b.m4a');

      final state = container.read(voicePlayerManagerProvider);
      expect(state.activeMessageId, 'msg_2');
      expect(backend.stopCount, greaterThanOrEqualTo(2));
      expect(backend.setSourceCount, 2);
      expect(backend.playCount, 2);
    });

    test('播放 backend 失败时展示统一不可播放态', () async {
      final analytics = _FakeAnalyticsService();
      final backend = _FakeVoicePlaybackBackend(throwOnSetSource: true);
      final container = ProviderContainer(
        overrides: [
          voicePlaybackBackendProvider.overrideWithValue(backend),
          voicePlaybackSourceResolverProvider.overrideWithValue(
            _fakeSourceResolver,
          ),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);

      await container
          .read(voicePlayerManagerProvider.notifier)
          .play('msg_1', 'https://cdn.example.com/a.m4a');

      final state = container.read(voicePlayerManagerProvider);
      expect(state.failedMessageId, 'msg_1');
      expect(state.error, UITextConstants.chatVoicePlayUnavailable);
      expect(
        analytics.events.map((event) => event.eventName),
        contains('voice_playback_failed'),
      );
    });
  });
}

Future<VoicePlaybackSourceResult> _fakeSourceResolver(String url) async {
  return VoicePlaybackSourceResult(
    source: AudioSource.uri(Uri.parse(url)),
    cacheHit: false,
  );
}

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

class _FakeVoicePlaybackBackend implements VoicePlaybackBackend {
  _FakeVoicePlaybackBackend({this.throwOnSetSource = false});

  final bool throwOnSetSource;
  int stopCount = 0;
  int setSourceCount = 0;
  int playCount = 0;

  final StreamController<PlayerState> _playerStateController =
      StreamController<PlayerState>.broadcast();
  final StreamController<Duration> _positionController =
      StreamController<Duration>.broadcast();
  final StreamController<Duration?> _durationController =
      StreamController<Duration?>.broadcast();

  @override
  Stream<PlayerState> get playerStateStream => _playerStateController.stream;

  @override
  Stream<Duration> get positionStream => _positionController.stream;

  @override
  Stream<Duration?> get durationStream => _durationController.stream;

  @override
  Future<void> configure() async {}

  @override
  Future<void> setSource(AudioSource source) async {
    setSourceCount++;
    if (throwOnSetSource) {
      throw StateError('set source failed');
    }
  }

  @override
  Future<void> play() async {
    playCount++;
  }

  @override
  Future<void> pause() async {}

  @override
  Future<void> stop() async {
    stopCount++;
  }

  @override
  Future<void> seek(Duration position) async {}

  @override
  Future<void> dispose() async {
    await _playerStateController.close();
    await _positionController.close();
    await _durationController.close();
  }
}
