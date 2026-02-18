class AssistantRunMessage {
  const AssistantRunMessage({
    required this.role,
    required this.content,
  });

  final String role;
  final String content;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'role': role,
      'content': content,
    };
  }

  factory AssistantRunMessage.fromJson(Map<String, dynamic> json) {
    return AssistantRunMessage(
      role: (json['role'] as String?)?.trim() ?? 'user',
      content: (json['content'] as String?) ?? '',
    );
  }
}

class AssistantRunRequest {
  const AssistantRunRequest({
    required this.messages,
    this.sessionId,
    this.userId,
    this.deviceProfile = 'mobile',
    this.channel = 'app',
    this.traceId,
    this.maxIterations = 6,
    this.capabilityCatalog = const <String>[],
    this.contextScopeHint = const <String, dynamic>{},
    this.privacyProfile = 'default',
    this.privacyPolicy = const <String, dynamic>{},
  });

  final List<AssistantRunMessage> messages;
  final String? sessionId;
  final String? userId;
  final String deviceProfile;
  final String channel;
  final String? traceId;
  final int maxIterations;
  final List<String> capabilityCatalog;
  final Map<String, dynamic> contextScopeHint;
  final String privacyProfile;
  final Map<String, dynamic> privacyPolicy;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'messages': messages.map((m) => m.toJson()).toList(growable: false),
      'sessionId': sessionId,
      'userId': userId,
      'deviceProfile': deviceProfile,
      'channel': channel,
      'traceId': traceId,
      'maxIterations': maxIterations,
      'capabilityCatalog': capabilityCatalog,
      'contextScopeHint': contextScopeHint,
      'privacyProfile': privacyProfile,
      'privacyPolicy': privacyPolicy,
    };
  }

  factory AssistantRunRequest.fromJson(Map<String, dynamic> json) {
    final rawMessages = (json['messages'] as List?) ?? const <dynamic>[];
    return AssistantRunRequest(
      messages: rawMessages
          .whereType<Map>()
          .map(
            (m) => AssistantRunMessage.fromJson(
              m.cast<String, dynamic>(),
            ),
          )
          .toList(growable: false),
      sessionId: json['sessionId'] as String?,
      userId: json['userId'] as String?,
      deviceProfile: (json['deviceProfile'] as String?)?.trim().isNotEmpty == true
          ? (json['deviceProfile'] as String).trim()
          : 'mobile',
      channel: (json['channel'] as String?)?.trim().isNotEmpty == true
          ? (json['channel'] as String).trim()
          : 'app',
      traceId: (json['traceId'] as String?)?.trim(),
      maxIterations: (json['maxIterations'] as int?) ?? 6,
      capabilityCatalog: (json['capabilityCatalog'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      contextScopeHint: (json['contextScopeHint'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      privacyProfile: (json['privacyProfile'] as String?)?.trim().isNotEmpty == true
          ? (json['privacyProfile'] as String).trim()
          : 'default',
      privacyPolicy: (json['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }
}
