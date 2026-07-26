import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 云端会话历史快照：conversationId 供续聊绑定，transcript 按时间正序。
class AssistantHistorySnapshot {
  const AssistantHistorySnapshot({
    required this.conversationId,
    required this.topicTitle,
    required this.transcript,
  });

  final String conversationId;
  final String topicTitle;
  final List<AssistantTranscriptTimelineRow> transcript;
}

abstract class AssistantHistoryLoader {
  const AssistantHistoryLoader();

  /// 恢复最近一个会话的 transcript；[conversationId] 非空时恢复指定会话。
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  });
}

/// 云端历史恢复（R-ASSIST-001 收口）：消费 ListAssistantConversations /
/// ListConversationTurns 查询面，替代已删除的本地 AssistantSessionStore 双模型。
class CloudAssistantHistoryLoader implements AssistantHistoryLoader {
  const CloudAssistantHistoryLoader(this._facet);

  final AssistantConversationRunFacet _facet;

  @override
  Future<AssistantHistorySnapshot?> load({
    required String subAccountId,
    String conversationId = '',
  }) async {
    var targetConversationId = conversationId.trim();
    var topicTitle = '';
    if (targetConversationId.isEmpty) {
      final conversations = await _facet.listAssistantConversations(limit: 1);
      if (conversations.items.isEmpty) {
        return null;
      }
      final latest = conversations.items.first;
      targetConversationId = latest.conversationId;
      topicTitle = latest.summary;
    }
    final turnsView = await _facet.listConversationTurns(
      conversationId: targetConversationId,
    );
    if (turnsView.items.isEmpty) {
      return AssistantHistorySnapshot(
        conversationId: targetConversationId,
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
            conversationId: AppConceptConstants.assistantConversationId,
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
            conversationId: AppConceptConstants.assistantConversationId,
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
            conversationId: AppConceptConstants.assistantConversationId,
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
            conversationId: AppConceptConstants.assistantConversationId,
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
      conversationId: targetConversationId,
      topicTitle: topicTitle,
      transcript: transcript,
    );
  }
}

final assistantHistoryLoaderProvider = Provider<AssistantHistoryLoader>(
  (ref) => CloudAssistantHistoryLoader(
    ref.watch(assistantConversationRunFacetProvider),
  ),
);
