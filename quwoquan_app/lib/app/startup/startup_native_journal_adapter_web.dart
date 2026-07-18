import 'dart:convert';
import 'dart:js_interop';

final class NativeStartupJournalPayload {
  const NativeStartupJournalPayload({
    required this.attemptId,
    required this.events,
  });

  final String attemptId;
  final List<String> events;
}

@JS('__qwqReadStartupJournal')
external JSPromise<JSString> _readStartupJournal();

@JS('__qwqClearStartupJournal')
external void _clearStartupJournal();

Future<NativeStartupJournalPayload> readStartupNativeJournal() async {
  try {
    final raw = (await _readStartupJournal().toDart).toDart;
    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      return const NativeStartupJournalPayload(attemptId: '', events: []);
    }
    final rawEvents = decoded['events'];
    return NativeStartupJournalPayload(
      attemptId: decoded['attemptId']?.toString() ?? '',
      events: rawEvents is List
          ? rawEvents.map((event) => event.toString()).toList(growable: false)
          : const <String>[],
    );
  } catch (_) {
    return const NativeStartupJournalPayload(attemptId: '', events: []);
  }
}

Future<void> clearStartupNativeJournal() async {
  try {
    _clearStartupJournal();
  } catch (_) {
    // Web native-like journal unavailable must not prevent Flutter bootstrap.
  }
}
