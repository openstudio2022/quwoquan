import 'package:quwoquan_app/core/platform/startup_native_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _eventsKey = 'startup_telemetry_native_journal';
const _attemptKey = 'startup_telemetry_native_attempt';

final class NativeStartupJournalPayload {
  const NativeStartupJournalPayload({
    required this.attemptId,
    required this.events,
  });

  final String attemptId;
  final List<String> events;
}

Future<NativeStartupJournalPayload> readStartupNativeJournal() async {
  final nativeEntries = await const MethodChannelStartupJournalNativeBridge()
      .readEntries();
  if (nativeEntries != null) {
    return NativeStartupJournalPayload(
      attemptId: nativeEntries.attemptId,
      events: nativeEntries.events,
    );
  }
  final preferences = await SharedPreferences.getInstance();
  return NativeStartupJournalPayload(
    attemptId: preferences.getString(_attemptKey) ?? '',
    events: List<String>.from(
      preferences.getStringList(_eventsKey) ?? const <String>[],
    ),
  );
}

Future<void> clearStartupNativeJournal() async {
  if (await const MethodChannelStartupJournalNativeBridge().clearEntries()) {
    return;
  }
  final preferences = await SharedPreferences.getInstance();
  await preferences.remove(_eventsKey);
}
