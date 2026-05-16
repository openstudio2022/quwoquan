import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';

/// 时间轴行 Map ↔ 强类型 Row（单一编解码边界）。
class PersistedTimelineTurnCodec {
  PersistedTimelineTurnCodec._();

  static Set<String> get _managedKeys => {
        ...kTranscriptEnvelopeKeys,
        ...kTranscriptAnchorKeys,
        ...kTranscriptAssistantBlobKeys,
        ...kPersistedAssistantTimelinePayloadKeys,
      };

  static Map<String, dynamic> _extractExtra(Map<String, dynamic> m) {
    final out = <String, dynamic>{};
    for (final e in m.entries) {
      if (_managedKeys.contains(e.key)) continue;
      out[e.key] = _cloneJson(e.value);
    }
    return out;
  }

  static List<Map<String, dynamic>> _decodeUiReferencesList(dynamic refs) {
    if (refs is! List) return const <Map<String, dynamic>>[];
    return refs
        .whereType<Map>()
        .map((e) => e.cast<String, dynamic>())
        .toList(growable: false);
  }

  static dynamic _cloneJson(dynamic v) {
    if (v is Map) {
      return v.map((k, val) => MapEntry(k.toString(), _cloneJson(val)));
    }
    if (v is List) {
      return v.map(_cloneJson).toList(growable: false);
    }
    return v;
  }

  static AssistantTranscriptTimelineRow decode(Map<String, dynamic> m) {
    final extra = _extractExtra(m);
    if (m['isError'] == true) {
      return ErrorTranscriptTimelineRow(
        id: (m['id'] as String?) ?? '',
        conversationId: (m['conversationId'] as String?) ?? '',
        content: (m['content'] as String?) ?? '',
        senderId: (m['senderId'] as String?) ?? '',
        senderName: (m['senderName'] as String?) ?? '',
        senderAvatar: (m['senderAvatar'] as String?) ?? '',
        timestamp: (m['timestamp'] as String?) ?? '',
        extra: extra,
      );
    }
    if (m['isSelf'] == true) {
      return UserTranscriptTimelineRow(
        id: (m['id'] as String?) ?? '',
        conversationId: (m['conversationId'] as String?) ?? '',
        type: (m['type'] as String?) ?? 'text',
        content: (m['content'] as String?) ?? '',
        senderId: (m['senderId'] as String?) ?? '',
        senderName: (m['senderName'] as String?) ?? '',
        senderAvatar: (m['senderAvatar'] as String?) ?? '',
        senderSubAccountId:
            (m['senderSubAccountId'] as String?) ??
            (m['senderPersonaId'] as String?) ??
            '',
        timestamp: (m['timestamp'] as String?) ?? '',
        status: (m['status'] as String?) ?? '',
        isRead: m['isRead'] as bool? ?? true,
        extra: extra,
      );
    }
    final anchor = AssistantAnswerAnchor(
      runId: (m['runId'] as String?) ?? '',
      traceId: (m['traceId'] as String?) ?? '',
      sourceQuery: (m['sourceQuery'] as String?) ?? '',
      templateVersionUsed: (m['templateVersionUsed'] as String?) ?? '',
      phaseOneRoutingDiagnostics:
          (m['phaseOneRoutingDiagnostics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      degraded: m['degraded'] as bool? ?? false,
      qualityMetrics:
          (m['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      heuristicFallbackUsed: m['heuristicFallbackUsed'] as bool? ?? false,
      domainId: (m['domainId'] as String?) ?? '',
    );
    final uiActionsRaw = m['uiActions'];
    final uiActionsList = uiActionsRaw is List
        ? uiActionsRaw
              .whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(growable: false)
        : uiActionsRaw is Map
        ? <Map<String, dynamic>>[uiActionsRaw.cast<String, dynamic>()]
        : const <Map<String, dynamic>>[];
    return AssistantAnswerTranscriptRow(
      id: (m['id'] as String?) ?? '',
      conversationId: (m['conversationId'] as String?) ?? '',
      type: (m['type'] as String?) ?? 'text',
      content: (m['content'] as String?) ?? '',
      senderId: (m['senderId'] as String?) ?? '',
      senderName: (m['senderName'] as String?) ?? '',
      senderAvatar: (m['senderAvatar'] as String?) ?? '',
      timestamp: (m['timestamp'] as String?) ?? '',
      isRead: m['isRead'] as bool? ?? true,
      streaming: m['streaming'] as bool? ?? false,
      streamFinalAnswer: (m['streamFinalAnswer'] as String?) ?? '',
      anchor: anchor,
      persisted: PersistedAssistantTimelinePayload.fromMap(m),
      dialogueState:
          (m['dialogueState'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      uiReferences: _decodeUiReferencesList(m['uiReferences']),
      uiActions: uiActionsList,
      runArtifacts:
          (m['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      uiUsageStats:
          (m['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      extra: extra,
    );
  }

  static Map<String, dynamic> encode(AssistantTranscriptTimelineRow row) {
    return switch (row) {
      UserTranscriptTimelineRow r => {
          ...r.extra,
          'id': r.id,
          'conversationId': r.conversationId,
          'type': r.type,
          'content': r.content,
          'senderId': r.senderId,
          'senderName': r.senderName,
          'senderAvatar': r.senderAvatar,
          if (r.senderSubAccountId.isNotEmpty)
            'senderSubAccountId': r.senderSubAccountId,
          'timestamp': r.timestamp,
          if (r.status.isNotEmpty) 'status': r.status,
          'isRead': r.isRead,
          'isSelf': true,
        },
      ErrorTranscriptTimelineRow r => {
          ...r.extra,
          'id': r.id,
          'conversationId': r.conversationId,
          'type': 'text',
          'content': r.content,
          'senderId': r.senderId,
          'senderName': r.senderName,
          'senderAvatar': r.senderAvatar,
          'timestamp': r.timestamp,
          'isRead': true,
          'isSelf': false,
          'isError': true,
        },
      AssistantAnswerTranscriptRow r => {
          ...r.extra,
          'id': r.id,
          'conversationId': r.conversationId,
          'type': r.type,
          'content': r.content,
          'senderId': r.senderId,
          'senderName': r.senderName,
          'senderAvatar': r.senderAvatar,
          'timestamp': r.timestamp,
          'isRead': r.isRead,
          'isSelf': false,
          'streaming': r.streaming,
          'streamFinalAnswer': r.streamFinalAnswer,
          'runId': r.anchor.runId,
          'traceId': r.anchor.traceId,
          'sourceQuery': r.anchor.sourceQuery,
          'templateVersionUsed': r.anchor.templateVersionUsed,
          'phaseOneRoutingDiagnostics': r.anchor.phaseOneRoutingDiagnostics,
          'degraded': r.anchor.degraded,
          'qualityMetrics': r.anchor.qualityMetrics,
          'heuristicFallbackUsed': r.anchor.heuristicFallbackUsed,
          'domainId': r.anchor.domainId,
          'dialogueState': r.dialogueState,
          'uiReferences': r.uiReferences,
          'uiActions': r.uiActions,
          'runArtifacts': r.runArtifacts,
          'uiUsageStats': r.uiUsageStats,
          ...r.persisted.toMap(),
        },
    };
  }
}
