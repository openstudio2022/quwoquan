import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

class AssistantHistorySnapshot {
  const AssistantHistorySnapshot({
    required this.sessionId,
    required this.topicTitle,
    required this.transcript,
  });

  final String sessionId;
  final String topicTitle;
  final List<AssistantTranscriptTimelineRow> transcript;
}

abstract interface class AssistantHistoryLoader {
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  });
}
