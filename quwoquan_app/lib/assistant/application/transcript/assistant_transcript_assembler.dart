import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
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
