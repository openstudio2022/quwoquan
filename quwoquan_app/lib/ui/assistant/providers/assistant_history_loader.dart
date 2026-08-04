import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 云端会话历史快照：sessionId 供续聊绑定，transcript 按时间正序。
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

  /// 恢复最近一个会话的 transcript；[sessionId] 非空时恢复指定会话。
  Future<AssistantHistorySnapshot?> load({
    required String personaId,
    String sessionId = '',
  });
}

/// 云端历史恢复（R-ASSIST-001 收口）：消费 ListAssistantSessions /
/// ListSessionTurns 查询面，替代已删除的本地 AssistantSessionStore 双模型。
class CloudAssistantHistoryLoader implements AssistantHistoryLoader {
  const CloudAssistantHistoryLoader(this._facet);

  final AssistantSessionRunFacet _facet;

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

final assistantHistoryLoaderProvider = Provider<AssistantHistoryLoader>(
  (ref) =>
      CloudAssistantHistoryLoader(ref.watch(assistantSessionRunFacetProvider)),
);
