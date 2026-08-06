import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Stable RTC sink consumed by the realtime connection object.
abstract interface class RealtimeRtcSignalSink {
  void add(RealtimeEventEnvelope event);
}

bool isRealtimeRtcSignalWireType(String type) {
  return type.startsWith('call.') ||
      type.startsWith('participant.') ||
      type.startsWith('screen_share.');
}
