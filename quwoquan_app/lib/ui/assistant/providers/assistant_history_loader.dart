import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/session/session_transcript_service.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/ui/assistant/assistant_conversation_model_history_text.dart';

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

abstract class AssistantHistoryLoader {
  const AssistantHistoryLoader();

  Future<AssistantHistorySnapshot?> load({required String profileSubjectId});
}

class LocalAssistantHistoryLoader implements AssistantHistoryLoader {
  const LocalAssistantHistoryLoader();

  @override
  Future<AssistantHistorySnapshot?> load({
    required String profileSubjectId,
  }) async {
    if (_shouldSkipLocalLoad()) {
      return null;
    }
    final sessionManager = AssistantSessionManager();
    await sessionManager.load();
    final sessionId = _selectSessionId(sessionManager);
    if (sessionId.isEmpty) {
      return null;
    }
    final detail = _sessionDetailFor(sessionManager, sessionId);
    if (detail == null || detail.messages.isEmpty) {
      return null;
    }
    final result = await loadTranscriptRowsFromSessionDetail(
      detail: detail,
      pageSize: detail.messages.length,
      profileSubjectId: profileSubjectId,
      normalizeAssistantContentForModel:
          assistantHistoryTextForModelFromMessageMap,
    );
    final transcript = <AssistantTranscriptTimelineRow>[
      ...result.hiddenRows,
      ...result.visibleRows,
    ];
    if (transcript.isEmpty) {
      return null;
    }
    return AssistantHistorySnapshot(
      sessionId: sessionId,
      topicTitle: detail.topicTitle,
      transcript: transcript,
    );
  }

  String _selectSessionId(AssistantSessionManager sessionManager) {
    final activeSessionId = sessionManager
        .ensureAssistantActiveSession()
        .trim();
    final activeMessages = sessionManager.sessions[activeSessionId];
    if (activeSessionId.isNotEmpty &&
        activeMessages != null &&
        activeMessages.isNotEmpty) {
      return activeSessionId;
    }
    for (final descriptor in sessionManager.listSessionDescriptors()) {
      final messages = sessionManager.sessions[descriptor.sessionId];
      if (messages != null && messages.isNotEmpty) {
        return descriptor.sessionId;
      }
    }
    for (final entry in sessionManager.sessions.entries) {
      if (entry.value.isNotEmpty) {
        return entry.key;
      }
    }
    return '';
  }

  AssistantSessionWireDetail? _sessionDetailFor(
    AssistantSessionManager sessionManager,
    String sessionId,
  ) {
    final messages = sessionManager.sessions[sessionId];
    if (messages == null || messages.isEmpty) {
      return null;
    }
    return AssistantSessionWireDetail(
      sessionId: sessionId,
      summary: sessionManager.summarizeRecent(sessionId),
      topicTitle: sessionManager.topicTitleOf(sessionId),
      messages: messages
          .map(AssistantSessionWireMessage.fromJson)
          .toList(growable: false),
      sessionPreferenceFacts: sessionManager
          .sessionPreferenceFactsOf(sessionId)
          .map((item) => item.toJson())
          .toList(growable: false),
      longTermPreferenceFacts: sessionManager
          .longTermPreferenceFactsOf(sessionId)
          .map((item) => item.toJson())
          .toList(growable: false),
    );
  }

  bool _shouldSkipLocalLoad() {
    try {
      final bindingType = WidgetsBinding.instance.runtimeType.toString();
      return bindingType.contains('Test') ||
          bindingType.contains('Integration');
    } catch (_) {
      return true;
    }
  }
}

final assistantHistoryLoaderProvider = Provider<AssistantHistoryLoader>(
  (ref) => const LocalAssistantHistoryLoader(),
);
