import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_ui_usage_stats_view_data.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart'
    show RunArtifacts;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_answer_anchor.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_citation.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/transcript_line_id.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/utterance_send_state.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/user_utterance.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantRunTerminalSnapshotView;

/// 受 Codec 管理的非持久化键（其余进入 [extra] 以保证 round-trip）。
const Set<String> kTranscriptEnvelopeKeys = {
  'id',
  'sessionId',
  'type',
  'content',
  'senderId',
  'senderName',
  'senderAvatar',
  'senderPersonaId',
  'timestamp',
  'status',
  'isRead',
  'isSelf',
  'streaming',
  'isError',
};

const Set<String> kTranscriptAnchorKeys = {
  'runId',
  'traceId',
  'sourceQuery',
  'templateVersionUsed',
  'phaseOneRoutingDiagnostics',
  'degraded',
  'qualityMetrics',
  'heuristicFallbackUsed',
  'domainId',
};

const Set<String> kTranscriptAssistantBlobKeys = {
  'uiReferences',
  'runArtifacts',
  'uiUsageStats',
};

/// 已退役的历史协议键：Codec 解码时丢弃，禁止经 [extra] 兜底回流。
/// `dialogueState` / `uiActions` 为零业务消费死袋，
/// `assistantBoundaryOutcome` 为零写入方死键。
const Set<String> kTranscriptRetiredKeys = {
  'dialogueState',
  'uiActions',
  'assistantBoundaryOutcome',
};

/// 时间轴行（sealed）：用户 / 助手 / 错误。
sealed class AssistantTranscriptTimelineRow {
  const AssistantTranscriptTimelineRow();

  TranscriptLineId get id;
}

final class UserTranscriptTimelineRow extends AssistantTranscriptTimelineRow {
  UserTranscriptTimelineRow({
    required this.id,
    required this.sessionId,
    this.type = 'text',
    required this.content,
    required this.senderId,
    required this.senderName,
    this.senderAvatar = '',
    this.senderPersonaId = '',
    this.timestamp = '',
    this.status = '',
    this.isRead = true,
    UtteranceSendState? sendState,
    this.extra = const <String, dynamic>{},
  }) : sendState =
           sendState ??
           (status == 'sending'
               ? UtteranceSendState.sending
               : UtteranceSendState.sent);

  @override
  final TranscriptLineId id;
  final String sessionId;
  final String type;
  final String content;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String senderPersonaId;
  final String timestamp;
  final String status;
  final bool isRead;
  final UtteranceSendState sendState;
  final Map<String, dynamic> extra;

  UserUtterance get utterance => UserUtterance(
    text: content,
    personaId: senderPersonaId,
    sendState: sendState,
  );
}

final class AssistantAnswerTranscriptRow
    extends AssistantTranscriptTimelineRow {
  AssistantAnswerTranscriptRow({
    required this.id,
    required this.sessionId,
    this.type = 'text',
    required this.content,
    required this.senderId,
    required this.senderName,
    this.senderAvatar = '',
    this.timestamp = '',
    this.isRead = true,
    this.streaming = false,
    this.anchor = const AssistantAnswerAnchor(),
    this.terminalSnapshot,
    PersistedAssistantTimelinePayload? persisted,
    this.uiReferences = const <AssistantCitation>[],
    this.runArtifacts,
    this.uiUsageStats = AssistantUiUsageStatsViewData.empty,
    this.extra = const <String, dynamic>{},
  }) : persisted = persisted ?? PersistedAssistantTimelinePayload.empty();

  @override
  final TranscriptLineId id;
  final String sessionId;
  final String type;
  final String content;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String timestamp;
  final bool isRead;
  final bool streaming;
  final AssistantAnswerAnchor anchor;
  final AssistantRunTerminalSnapshotView? terminalSnapshot;
  final PersistedAssistantTimelinePayload persisted;

  final List<AssistantCitation> uiReferences;

  /// 运行工件（含 `presentationDocument` 与 partitioned diagnostics）；
  /// null 表示无工件，解析失败在 Codec 边界 fail-soft 置 null。
  final RunArtifacts? runArtifacts;
  final AssistantUiUsageStatsViewData uiUsageStats;
  final Map<String, dynamic> extra;

  AssistantAnswerTranscriptRow copyWith({
    String? id,
    String? sessionId,
    String? type,
    String? content,
    String? senderId,
    String? senderName,
    String? senderAvatar,
    String? timestamp,
    bool? isRead,
    bool? streaming,
    AssistantAnswerAnchor? anchor,
    AssistantRunTerminalSnapshotView? terminalSnapshot,
    PersistedAssistantTimelinePayload? persisted,
    List<AssistantCitation>? uiReferences,
    RunArtifacts? runArtifacts,
    AssistantUiUsageStatsViewData? uiUsageStats,
    Map<String, dynamic>? extra,
  }) {
    return AssistantAnswerTranscriptRow(
      id: id ?? this.id,
      sessionId: sessionId ?? this.sessionId,
      type: type ?? this.type,
      content: content ?? this.content,
      senderId: senderId ?? this.senderId,
      senderName: senderName ?? this.senderName,
      senderAvatar: senderAvatar ?? this.senderAvatar,
      timestamp: timestamp ?? this.timestamp,
      isRead: isRead ?? this.isRead,
      streaming: streaming ?? this.streaming,
      anchor: anchor ?? this.anchor,
      terminalSnapshot: terminalSnapshot ?? this.terminalSnapshot,
      persisted: persisted ?? this.persisted,
      uiReferences: uiReferences ?? this.uiReferences,
      runArtifacts: runArtifacts ?? this.runArtifacts,
      uiUsageStats: uiUsageStats ?? this.uiUsageStats,
      extra: extra ?? this.extra,
    );
  }
}

final class ErrorTranscriptTimelineRow extends AssistantTranscriptTimelineRow {
  ErrorTranscriptTimelineRow({
    required this.id,
    required this.sessionId,
    required this.content,
    required this.senderId,
    required this.senderName,
    this.senderAvatar = '',
    this.timestamp = '',
    this.extra = const <String, dynamic>{},
  });

  @override
  final TranscriptLineId id;
  final String sessionId;
  final String content;
  final String senderId;
  final String senderName;
  final String senderAvatar;
  final String timestamp;
  final Map<String, dynamic> extra;
}
