import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_ui_usage_stats_view_data.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart'
    show RunArtifacts;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_answer_anchor.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_citation.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

/// 时间轴行 Map ↔ 强类型 Row（单一编解码边界）。
class PersistedTimelineTurnCodec {
  PersistedTimelineTurnCodec._();

  static Set<String> get _managedKeys => {
    ...kTranscriptEnvelopeKeys,
    ...kTranscriptAnchorKeys,
    ...kTranscriptAssistantBlobKeys,
    ...kTranscriptRetiredKeys,
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

  /// 运行工件为诊断性数据：结构非法时 fail-soft 置 null，不阻断整行解码。
  static RunArtifacts? _decodeRunArtifacts(dynamic raw) {
    if (raw is! Map) return null;
    final map = raw.cast<String, dynamic>();
    if (map.isEmpty) return null;
    try {
      return RunArtifacts.fromJson(map);
    } on FormatException {
      return null;
    }
  }

  /// 解析失败的引用被丢弃（fail-closed，与 UI 只渲染有效引用一致）。
  static List<AssistantCitation> _decodeUiReferencesList(dynamic refs) {
    if (refs is! List) return const <AssistantCitation>[];
    return refs
        .whereType<Map>()
        .map(
          (e) => AssistantCitation.tryFromReferenceMap(
            e.cast<String, dynamic>(),
          ),
        )
        .whereType<AssistantCitation>()
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
        sessionId: (m['sessionId'] as String?) ?? '',
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
        sessionId: (m['sessionId'] as String?) ?? '',
        type: (m['type'] as String?) ?? 'text',
        content: (m['content'] as String?) ?? '',
        senderId: (m['senderId'] as String?) ?? '',
        senderName: (m['senderName'] as String?) ?? '',
        senderAvatar: (m['senderAvatar'] as String?) ?? '',
        senderPersonaId: (m['senderPersonaId'] as String?) ?? '',
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
    return AssistantAnswerTranscriptRow(
      id: (m['id'] as String?) ?? '',
      sessionId: (m['sessionId'] as String?) ?? '',
      type: (m['type'] as String?) ?? 'text',
      content: (m['content'] as String?) ?? '',
      senderId: (m['senderId'] as String?) ?? '',
      senderName: (m['senderName'] as String?) ?? '',
      senderAvatar: (m['senderAvatar'] as String?) ?? '',
      timestamp: (m['timestamp'] as String?) ?? '',
      isRead: m['isRead'] as bool? ?? true,
      streaming: m['streaming'] as bool? ?? false,
      anchor: anchor,
      persisted: PersistedAssistantTimelinePayload.fromMap(m),
      uiReferences: _decodeUiReferencesList(m['uiReferences']),
      runArtifacts: _decodeRunArtifacts(m['runArtifacts']),
      uiUsageStats: AssistantUiUsageStatsViewData.fromProtocolMap(
        (m['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      extra: extra,
    );
  }

  static Map<String, dynamic> encode(AssistantTranscriptTimelineRow row) {
    return switch (row) {
      UserTranscriptTimelineRow r => {
        ...r.extra,
        'id': r.id,
        'sessionId': r.sessionId,
        'type': r.type,
        'content': r.content,
        'senderId': r.senderId,
        'senderName': r.senderName,
        'senderAvatar': r.senderAvatar,
        if (r.senderPersonaId.isNotEmpty) 'senderPersonaId': r.senderPersonaId,
        'timestamp': r.timestamp,
        if (r.status.isNotEmpty) 'status': r.status,
        'isRead': r.isRead,
        'isSelf': true,
      },
      ErrorTranscriptTimelineRow r => {
        ...r.extra,
        'id': r.id,
        'sessionId': r.sessionId,
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
        'sessionId': r.sessionId,
        'type': r.type,
        'content': r.content,
        'senderId': r.senderId,
        'senderName': r.senderName,
        'senderAvatar': r.senderAvatar,
        'timestamp': r.timestamp,
        'isRead': r.isRead,
        'isSelf': false,
        'streaming': r.streaming,
        'runId': r.anchor.runId,
        'traceId': r.anchor.traceId,
        'sourceQuery': r.anchor.sourceQuery,
        'templateVersionUsed': r.anchor.templateVersionUsed,
        'phaseOneRoutingDiagnostics': r.anchor.phaseOneRoutingDiagnostics,
        'degraded': r.anchor.degraded,
        'qualityMetrics': r.anchor.qualityMetrics,
        'heuristicFallbackUsed': r.anchor.heuristicFallbackUsed,
        'domainId': r.anchor.domainId,
        'uiReferences': r.uiReferences
            .map((citation) => citation.toReferenceMap())
            .toList(growable: false),
        if (r.runArtifacts != null) 'runArtifacts': r.runArtifacts!.toJson(),
        'uiUsageStats': r.uiUsageStats.toProtocolMap(),
        ...r.persisted.toMap(),
      },
    };
  }
}
