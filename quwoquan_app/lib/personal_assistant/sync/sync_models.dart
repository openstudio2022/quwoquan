import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';

enum AssistentSyncResource {
  policy,
  interactionEvents,
  scorecards,
  memoryRecords,
}

class AssistentSyncResult {
  const AssistentSyncResult({
    required this.success,
    required this.mode,
    required this.resource,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final bool success;
  final AssistentSyncMode mode;
  final AssistentSyncResource resource;
  final String message;
  final Map<String, dynamic> payload;
}

