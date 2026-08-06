import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';

class VoiceMessageEventNames {
  static const String recordInvalid = 'voice_record_invalid';
  static const String uploadStarted = 'voice_upload_started';
  static const String uploadSucceeded = 'voice_upload_succeeded';
  static const String uploadFailed = 'voice_upload_failed';
  static const String sendStarted = 'voice_send_started';
  static const String sendSucceeded = 'voice_send_succeeded';
  static const String sendFailed = 'voice_send_failed';
  static const String playbackStarted = 'voice_playback_started';
  static const String playbackPaused = 'voice_playback_paused';
  static const String playbackStopped = 'voice_playback_stopped';
  static const String playbackFailed = 'voice_playback_failed';

  const VoiceMessageEventNames._();
}

class VoiceMessageObservability {
  VoiceMessageObservability({required this._analytics});

  final AnalyticsService _analytics;

  void trackAction({
    required String eventName,
    String? conversationId,
    String? messageId,
    int? durationMs,
    int? fileSizeBytes,
    int? waveformSamples,
    double? uploadProgress,
    String? failureKind,
    bool? cacheHit,
  }) {
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'voice_message_action',
          eventName: eventName,
          properties: <String, dynamic>{
            'conversationId': ?conversationId,
            'messageId': ?messageId,
            'durationMs': ?durationMs,
            'fileSizeBytes': ?fileSizeBytes,
            'waveformSamples': ?waveformSamples,
            'uploadProgress': ?uploadProgress,
            'failureKind': ?failureKind,
            'cacheHit': ?cacheHit,
          },
        ),
      ),
    );
  }
}

final voiceMessageObservabilityProvider = Provider<VoiceMessageObservability>((
  ref,
) {
  return VoiceMessageObservability(analytics: ref.read(analyticsProvider));
});
