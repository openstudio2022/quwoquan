import 'dart:math' as math;

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';

/// 从 [AssistantSessionWireDetail] 构建时间轴行（分页与 Controller 记录加载一致）。
class AssistantSessionHistoryLoadResult {
  const AssistantSessionHistoryLoadResult({
    required this.visibleRows,
    required this.hiddenRows,
  });

  final List<AssistantTranscriptTimelineRow> visibleRows;
  final List<AssistantTranscriptTimelineRow> hiddenRows;
}

/// Map 拼装封闭在此；仅输出强类型时间轴行。
Future<AssistantSessionHistoryLoadResult> loadTranscriptRowsFromSessionDetail({
  required AssistantSessionWireDetail detail,
  required int pageSize,
  required String profileSubjectId,
  required String Function(Map<String, dynamic> wire)
  normalizeAssistantContentForModel,
}) async {
  final sessionId = detail.sessionId;
  final messages = detail.messages;
  final now = DateTime.now();
  var serial = 0;
  final mapped = messages
      .map((wire) {
        final item = wire.raw;
        final isUser = wire.role == 'user';
        final normalizedContent = isUser
            ? wire.content
            : normalizeAssistantContentForModel(item);
        final hasPersistedTurn =
            !isUser &&
            (!resolvePersistedAssistantTimeline(item).isEmpty ||
                isCanonicalPersistedAssistantTurnMessage(item));
        if (!isUser && normalizedContent.trim().isEmpty && !hasPersistedTurn) {
          return null;
        }
        serial += 1;
        return <String, dynamic>{
          ...item,
          'id': 'assistant_${sessionId}_$serial',
          'conversationId': AppConceptConstants.assistantConversationId,
          'type': 'text',
          'content': normalizedContent,
          'senderId': isUser
              ? profileSubjectId
              : AppConceptConstants.assistantSenderId,
          'senderName': isUser ? '我' : AppConceptConstants.assistantLabel,
          'senderAvatar': '',
          'timestamp': '${now.hour}:${now.minute.toString().padLeft(2, '0')}',
          'isRead': true,
          'isSelf': isUser,
        };
      })
      .whereType<Map<String, dynamic>>()
      .toList(growable: false);
  final splitIndex = math.max(0, mapped.length - pageSize);
  final hiddenMaps = mapped.sublist(0, splitIndex);
  final visibleMaps = mapped.sublist(splitIndex);
  return AssistantSessionHistoryLoadResult(
    hiddenRows: hiddenMaps
        .map(PersistedTimelineTurnCodec.decode)
        .toList(growable: false),
    visibleRows: visibleMaps
        .map(PersistedTimelineTurnCodec.decode)
        .toList(growable: false),
  );
}
