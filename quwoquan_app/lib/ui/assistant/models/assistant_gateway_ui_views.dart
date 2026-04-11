import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';

// 本地 Assistant Gateway 返回的会话/偏好快照在 UI 层的强类型视图（非 codegen）。

class AssistantLocalSessionSummaryView {
  const AssistantLocalSessionSummaryView({
    required this.sessionId,
    this.topicTitle = '',
    this.topicSummary = '',
    this.messageCount = 0,
    this.lastMessage = '',
  });

  final String sessionId;
  final String topicTitle;
  final String topicSummary;
  final int messageCount;
  final String lastMessage;

  factory AssistantLocalSessionSummaryView.fromDescriptor(
    AssistantSessionDescriptor d,
  ) {
    return AssistantLocalSessionSummaryView(
      sessionId: d.sessionId,
      topicTitle: d.topicTitle,
      topicSummary: d.topicSummary,
      messageCount: d.messageCount,
      lastMessage: d.lastMessage,
    );
  }

  @Deprecated('Use fromDescriptor for gateway listSessions results')
  factory AssistantLocalSessionSummaryView.fromMap(Map<String, dynamic> m) {
    return AssistantLocalSessionSummaryView.fromDescriptor(
      AssistantSessionDescriptor.fromJson(m),
    );
  }
}

class AssistantPreferenceFactView {
  const AssistantPreferenceFactView({
    required this.keyText,
    required this.valueText,
  });

  final String keyText;
  final String valueText;

  factory AssistantPreferenceFactView.fromMap(Map<String, dynamic> m) {
    return AssistantPreferenceFactView(
      keyText: (m['key'] ?? '').toString(),
      valueText: (m['value'] ?? '').toString(),
    );
  }
}

class AssistantSessionDetailView {
  const AssistantSessionDetailView({
    required this.sessionPreferenceFacts,
    required this.longTermPreferenceFacts,
  });

  final List<AssistantPreferenceFactView> sessionPreferenceFacts;
  final List<AssistantPreferenceFactView> longTermPreferenceFacts;

  factory AssistantSessionDetailView.fromMap(Map<String, dynamic>? raw) {
    final m = raw ?? const <String, dynamic>{};

    List<AssistantPreferenceFactView> parseFacts(String key) {
      return (m[key] as List?)
              ?.whereType<Map>()
              .map(
                (e) => AssistantPreferenceFactView.fromMap(
                  e.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <AssistantPreferenceFactView>[];
    }

    return AssistantSessionDetailView(
      sessionPreferenceFacts: parseFacts('sessionPreferenceFacts'),
      longTermPreferenceFacts: parseFacts('longTermPreferenceFacts'),
    );
  }

  factory AssistantSessionDetailView.fromWire(AssistantSessionWireDetail detail) {
    return AssistantSessionDetailView(
      sessionPreferenceFacts: detail.sessionPreferenceFacts
          .map(AssistantPreferenceFactView.fromMap)
          .toList(growable: false),
      longTermPreferenceFacts: detail.longTermPreferenceFacts
          .map(AssistantPreferenceFactView.fromMap)
          .toList(growable: false),
    );
  }
}
