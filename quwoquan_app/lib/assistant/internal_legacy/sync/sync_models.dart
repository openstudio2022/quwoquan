import 'package:quwoquan_app/assistant/internal_legacy/sync/sync_mode.dart';

enum AssistantSyncResource {
  policy,
  interactionEvents,
  scorecards,
  memoryRecords,
}

class AssistantSyncResult {
  const AssistantSyncResult({
    required this.success,
    required this.mode,
    required this.resource,
    required this.message,
    this.payload = const <String, dynamic>{},
  });

  final bool success;
  final AssistantSyncMode mode;
  final AssistantSyncResource resource;
  final String message;
  final Map<String, dynamic> payload;
}

