import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_answer_anchor.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_history.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/assistant_text_constants.dart';

/// 云端历史恢复（R-ASSIST-001 收口）：消费 ListAssistantSessions /
/// ListSessionTurns 查询面，替代已删除的本地 AssistantSessionStore 双模型。
class CloudAssistantHistoryLoader implements AssistantHistoryLoader {
  const CloudAssistantHistoryLoader(this._facet);

  final AssistantSessionRunFacade _facet;

  @override
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  }) async {
    var targetSessionId = sessionId.trim();
    var topicTitle = '';
    if (targetSessionId.isEmpty) {
      final sessions = await _facet.listAssistantSessions(limit: 1);
      if (sessions.items.isEmpty) {
        return null;
      }
      final latest = sessions.items.first;
      targetSessionId = latest.sessionId;
      topicTitle = latest.summary;
    }
    final turnsView = await _facet.listSessionTurns(sessionId: targetSessionId);
    if (turnsView.items.isEmpty) {
      return AssistantHistorySnapshot(
        sessionId: targetSessionId,
        topicTitle: topicTitle,
        transcript: const <AssistantTranscriptTimelineRow>[],
      );
    }
    // 服务端 createdAt desc；transcript 按时间正序渲染。
    final ordered = turnsView.items.reversed;
    final transcript = <AssistantTranscriptTimelineRow>[];
    for (final turn in ordered) {
      final question = turn.inputText.trim();
      if (question.isNotEmpty) {
        transcript.add(
          UserTranscriptTimelineRow(
            id: 'history_user_${turn.turnId}',
            sessionId: targetSessionId,
            type: 'text',
            content: question,
            senderId: 'current_user',
            senderName: AssistantText.assistantCurrentUserSenderName,
            timestamp: turn.createdAt,
            status: '',
            isRead: true,
          ),
        );
      }
      final terminalSnapshot = turn.terminalSnapshot;
      final answer = (terminalSnapshot?.answerText ?? '').trim();
      if (answer.isNotEmpty) {
        transcript.add(
          AssistantAnswerTranscriptRow(
            id: 'history_assistant_${turn.turnId}',
            sessionId: targetSessionId,
            content: answer,
            senderId: AppConceptConstants.assistantSenderId,
            senderName: AppConceptConstants.assistantLabel,
            timestamp: turn.completedAt ?? turn.createdAt,
            anchor: AssistantAnswerAnchor(
              runId: turn.turnId,
              sourceQuery: question,
              domainId: turn.domainId ?? 'assistant',
            ),
            terminalSnapshot: terminalSnapshot,
          ),
        );
      } else if (turn.status == 'failed' && terminalSnapshot?.failure != null) {
        transcript.add(
          AssistantAnswerTranscriptRow(
            id: 'history_assistant_${turn.turnId}',
            sessionId: targetSessionId,
            content: AssistantText.assistantUnavailable,
            senderId: AppConceptConstants.assistantSenderId,
            senderName: AppConceptConstants.assistantLabel,
            timestamp: turn.completedAt ?? turn.createdAt,
            anchor: AssistantAnswerAnchor(
              runId: turn.turnId,
              sourceQuery: question,
              domainId: turn.domainId ?? 'assistant',
            ),
            terminalSnapshot: terminalSnapshot,
          ),
        );
      } else if (turn.status == 'cancelled') {
        transcript.add(
          AssistantAnswerTranscriptRow(
            id: 'history_assistant_${turn.turnId}',
            sessionId: targetSessionId,
            content: AssistantText.assistantTaskStatusCancelled,
            senderId: AppConceptConstants.assistantSenderId,
            senderName: AppConceptConstants.assistantLabel,
            timestamp: turn.completedAt ?? turn.createdAt,
            anchor: AssistantAnswerAnchor(
              runId: turn.turnId,
              sourceQuery: question,
              domainId: turn.domainId ?? 'assistant',
            ),
            terminalSnapshot: terminalSnapshot,
          ),
        );
      }
    }
    return AssistantHistorySnapshot(
      sessionId: targetSessionId,
      topicTitle: topicTitle,
      transcript: transcript,
    );
  }
}
