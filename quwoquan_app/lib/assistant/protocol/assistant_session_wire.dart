/// Local/remote session detail before UI timeline mapping (S-UI).
/// [AssistantSessionWireMessage.raw] keeps unknown keys so spreads stay equivalent to `Map`.
library;

/// 会话列表项，与 [AssistantSessionManager.listSessionDescriptors] 的 Map 键一一对应（网关/UI/HTTP 同源）。
class AssistantSessionDescriptor {
  const AssistantSessionDescriptor({
    required this.sessionId,
    this.messageCount = 0,
    this.lastMessage = '',
    this.topicTitle = '',
    this.topicSummary = '',
    this.sessionPreferenceFactCount = 0,
    this.longTermPreferenceFactCount = 0,
    this.updatedAt = '',
    this.isActive = false,
  });

  final String sessionId;
  final int messageCount;
  final String lastMessage;
  final String topicTitle;
  final String topicSummary;
  final int sessionPreferenceFactCount;
  final int longTermPreferenceFactCount;
  final String updatedAt;
  final bool isActive;

  factory AssistantSessionDescriptor.fromJson(Map<String, dynamic> json) {
    return AssistantSessionDescriptor(
      sessionId: (json['sessionId'] ?? '').toString(),
      messageCount: (json['messageCount'] as num?)?.toInt() ?? 0,
      lastMessage: (json['lastMessage'] ?? '').toString(),
      topicTitle: (json['topicTitle'] ?? '').toString(),
      topicSummary: (json['topicSummary'] ?? '').toString(),
      sessionPreferenceFactCount:
          (json['sessionPreferenceFactCount'] as num?)?.toInt() ?? 0,
      longTermPreferenceFactCount:
          (json['longTermPreferenceFactCount'] as num?)?.toInt() ?? 0,
      updatedAt: (json['updatedAt'] ?? '').toString(),
      isActive: json['isActive'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'sessionId': sessionId,
        'messageCount': messageCount,
        'lastMessage': lastMessage,
        'topicTitle': topicTitle,
        'topicSummary': topicSummary,
        'sessionPreferenceFactCount': sessionPreferenceFactCount,
        'longTermPreferenceFactCount': longTermPreferenceFactCount,
        'updatedAt': updatedAt,
        'isActive': isActive,
      };
}

class AssistantSessionWireMessage {
  const AssistantSessionWireMessage._(this.raw);

  final Map<String, dynamic> raw;

  factory AssistantSessionWireMessage.fromJson(Map<String, dynamic> json) {
    return AssistantSessionWireMessage._(Map<String, dynamic>.from(json));
  }

  String get role => (raw['role'] ?? '').toString();

  String get content => (raw['content'] ?? '').toString();
}

/// Strongly-typed boundary for [AssistantGateway.sessionDetail] while preserving wire shape.
class AssistantSessionWireDetail {
  const AssistantSessionWireDetail({
    required this.sessionId,
    this.summary = '',
    this.topicTitle = '',
    required this.messages,
    this.sessionPreferenceFacts = const <Map<String, dynamic>>[],
    this.longTermPreferenceFacts = const <Map<String, dynamic>>[],
  });

  final String sessionId;
  final String summary;
  final String topicTitle;
  final List<AssistantSessionWireMessage> messages;
  final List<Map<String, dynamic>> sessionPreferenceFacts;
  final List<Map<String, dynamic>> longTermPreferenceFacts;

  factory AssistantSessionWireDetail.fromJson(Map<String, dynamic> json) {
    final rawMessages = (json['messages'] as List?) ?? const <dynamic>[];
    return AssistantSessionWireDetail(
      sessionId: (json['sessionId'] ?? '').toString(),
      summary: (json['summary'] ?? '').toString(),
      topicTitle: (json['topicTitle'] as String?)?.trim() ?? '',
      messages: rawMessages
          .whereType<Map>()
          .map(
            (m) =>
                AssistantSessionWireMessage.fromJson(m.cast<String, dynamic>()),
          )
          .toList(growable: false),
      sessionPreferenceFacts:
          (json['sessionPreferenceFacts'] as List?)
              ?.whereType<Map>()
              .map((m) => m.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      longTermPreferenceFacts:
          (json['longTermPreferenceFacts'] as List?)
              ?.whereType<Map>()
              .map((m) => m.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'sessionId': sessionId,
    'summary': summary,
    'topicTitle': topicTitle,
    'messages': messages.map((m) => m.raw).toList(growable: false),
    'sessionPreferenceFacts': sessionPreferenceFacts,
    'longTermPreferenceFacts': longTermPreferenceFacts,
  };
}
