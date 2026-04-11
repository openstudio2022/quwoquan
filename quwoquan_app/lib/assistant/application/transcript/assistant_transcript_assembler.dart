import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_dialogue_runtime_read_view.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';

/// 时间轴行工厂（application）：把 controller 中的字面 Map 构造收口为强类型。
class AssistantTranscriptAssembler {
  AssistantTranscriptAssembler._();

  static UserTranscriptTimelineRow userTextMessage({
    required String id,
    required String trimmedText,
    required String profileSubjectId,
    required String displayName,
    String avatarUrl = '',
    String subAccountId = '',
    String timestamp = '',
    String status = 'sending',
  }) {
    return UserTranscriptTimelineRow(
      id: id,
      conversationId: AppConceptConstants.assistantConversationId,
      type: 'text',
      content: trimmedText,
      senderId: profileSubjectId,
      senderName: displayName.isNotEmpty ? displayName : '我',
      senderAvatar: avatarUrl,
      senderPersonaId: subAccountId,
      timestamp: timestamp,
      status: status,
      isRead: true,
    );
  }

  static AssistantAnswerTranscriptRow assistantStreamingPlaceholder({
    required String id,
    required String streamTimestamp,
  }) {
    return AssistantAnswerTranscriptRow(
      id: id,
      conversationId: AppConceptConstants.assistantConversationId,
      type: 'text',
      content: '',
      senderId: AppConceptConstants.assistantSenderId,
      senderName: AppConceptConstants.assistantLabel,
      senderAvatar: '',
      timestamp: streamTimestamp,
      isRead: true,
      streaming: true,
      streamFinalAnswer: '',
      persisted: PersistedAssistantTimelinePayload.empty().copyWithMerged(
        <String, dynamic>{
          assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
          assistantDisplayMarkdownField: '',
          assistantDisplayPlainTextField: '',
          assistantJourneyField: const <String, dynamic>{},
          assistantUiProcessTimelineField: const <String, dynamic>{},
          assistantFollowupPromptField: '',
          assistantActionHintsField: const <String>[],
          'assistantElapsedMs': 0,
        },
      ),
      runArtifacts: const <String, dynamic>{},
    );
  }

  static AssistantAnswerTranscriptRow assistantStreamingPlaceholderWithSourceQuery({
    required String id,
    required String streamTimestamp,
    required String sourceQuery,
  }) {
    final base = assistantStreamingPlaceholder(
      id: id,
      streamTimestamp: streamTimestamp,
    );
    return base.copyWith(
      anchor: AssistantAnswerAnchor(sourceQuery: sourceQuery),
    );
  }

  /// 流式首帧：可选把 `displayState` 写入持久化子图（与 controller `_mapToRow` 等价路径）。
  static AssistantAnswerTranscriptRow assistantStreamingPlaceholderWithInitialDisplayState({
    required String id,
    required String streamTimestamp,
    AssistantDisplayState? initialDisplayState,
  }) {
    var row = assistantStreamingPlaceholder(id: id, streamTimestamp: streamTimestamp);
    if (initialDisplayState != null &&
        hasAssistantDisplayState(initialDisplayState)) {
      row = row.copyWith(
        persisted: row.persisted.copyWithMerged(<String, dynamic>{
          assistantDisplayStateField: initialDisplayState.toJson(),
        }),
      );
    }
    return row;
  }

  /// 完成一轮 run 后的助手回答行（合并流式占位或新建一行）。
  static AssistantAnswerTranscriptRow completedAssistantAnswerTranscriptRow({
    AssistantAnswerTranscriptRow? mergeFrom,
    required String newRowId,
    required String content,
    required String timestamp,
    required String sourceQuery,
    required String runId,
    required String traceId,
    required bool degraded,
    required String templateVersionUsed,
    required Map<String, dynamic> phaseOneRoutingDiagnostics,
    required Map<String, dynamic> qualityMetrics,
    required bool heuristicFallbackUsed,
    required Map<String, dynamic> dialogueState,
    required List<Map<String, dynamic>> uiReferences,
    required List<Map<String, dynamic>> uiActions,
    required Map<String, dynamic> mergedRunArtifacts,
    required Map<String, dynamic> uiUsageStats,
    required Map<String, dynamic> persistedTurnFields,
  }) {
    final domainId =
        AssistantDialogueRuntimeReadView(dialogueState).domainIdOrEmpty;
    final anchor = AssistantAnswerAnchor(
      runId: runId,
      traceId: traceId,
      sourceQuery: sourceQuery,
      templateVersionUsed: templateVersionUsed,
      phaseOneRoutingDiagnostics: phaseOneRoutingDiagnostics,
      degraded: degraded,
      qualityMetrics: qualityMetrics,
      heuristicFallbackUsed: heuristicFallbackUsed,
      domainId: domainId,
    );
    final persistedBase =
        mergeFrom?.persisted ?? PersistedAssistantTimelinePayload.empty();
    final nextPersisted = persistedBase.copyWithMerged(persistedTurnFields);

    if (mergeFrom != null) {
      return mergeFrom.copyWith(
        content: content,
        timestamp: timestamp,
        anchor: anchor,
        dialogueState: dialogueState,
        uiReferences: uiReferences,
        uiActions: uiActions,
        runArtifacts: mergedRunArtifacts,
        uiUsageStats: uiUsageStats,
        persisted: nextPersisted,
        streaming: false,
        streamFinalAnswer: '',
      );
    }

    return AssistantAnswerTranscriptRow(
      id: newRowId,
      conversationId: AppConceptConstants.assistantConversationId,
      type: 'text',
      content: content,
      senderId: AppConceptConstants.assistantSenderId,
      senderName: AppConceptConstants.assistantLabel,
      senderAvatar: '',
      timestamp: timestamp,
      isRead: true,
      streaming: false,
      streamFinalAnswer: '',
      anchor: anchor,
      persisted: nextPersisted,
      dialogueState: dialogueState,
      uiReferences: uiReferences,
      uiActions: uiActions,
      runArtifacts: mergedRunArtifacts,
      uiUsageStats: uiUsageStats,
    );
  }

  static ErrorTranscriptTimelineRow assistantErrorMessage({
    required String id,
    required String errorHint,
  }) {
    return ErrorTranscriptTimelineRow(
      id: id,
      conversationId: AppConceptConstants.assistantConversationId,
      content: errorHint,
      senderId: AppConceptConstants.assistantSenderId,
      senderName: AppConceptConstants.assistantLabel,
      senderAvatar: '',
      timestamp: '',
    );
  }

  static UserTranscriptTimelineRow userRewriteLabel({
    required String id,
    required String label,
    required String profileSubjectId,
    required String displayName,
    required String timestamp,
  }) {
    return UserTranscriptTimelineRow(
      id: id,
      conversationId: AppConceptConstants.assistantConversationId,
      type: 'text',
      content: label,
      senderId: profileSubjectId,
      senderName: displayName,
      senderAvatar: '',
      timestamp: timestamp,
      status: '',
      isRead: true,
    );
  }
}
