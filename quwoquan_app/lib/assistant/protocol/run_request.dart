class AssistantRunMessage {
  const AssistantRunMessage({required this.role, required this.content});

  final String role;
  final String content;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{'role': role, 'content': content};
  }

  factory AssistantRunMessage.fromJson(Map<String, dynamic> json) {
    return AssistantRunMessage(
      role: (json['role'] as String?)?.trim() ?? 'user',
      content: (json['content'] as String?) ?? '',
    );
  }
}

enum RewriteMode {
  regenerate,
  concise,
  detailed,
  casual,
  deepThink,
}

class RewriteInstruction {
  const RewriteInstruction({
    required this.mode,
    required this.originalQuery,
    required this.previousAnswer,
  });

  final RewriteMode mode;
  final String originalQuery;
  final String previousAnswer;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'mode': mode.name,
      'originalQuery': originalQuery,
      'previousAnswer': previousAnswer,
    };
  }

  factory RewriteInstruction.fromJson(Map<String, dynamic> json) {
    return RewriteInstruction(
      mode: RewriteMode.values.firstWhere(
        (m) => m.name == (json['mode'] as String? ?? ''),
        orElse: () => RewriteMode.regenerate,
      ),
      originalQuery: (json['originalQuery'] as String?) ?? '',
      previousAnswer: (json['previousAnswer'] as String?) ?? '',
    );
  }

  String get systemPromptInjection {
    switch (mode) {
      case RewriteMode.regenerate:
        return '用户对上一次的回答不满意，请基于同样的信息源重新组织答案，'
            '换一种思路和表达方式重新回答。保持准确性的同时提升可读性。';
      case RewriteMode.concise:
        return '用户希望更简洁的回答。请基于以下已有回答，精简为要点式回答，'
            '去除冗余解释，只保留核心结论和关键数据。字数控制在原回答的1/3以内。';
      case RewriteMode.detailed:
        return '用户希望更详细的回答。请基于以下已有回答进行扩展，'
            '补充更多背景信息、对比分析、具体数据和实际案例。使用表格、分步骤等结构化格式。';
      case RewriteMode.casual:
        return '用户希望更口语化的回答。请基于以下已有回答，'
            '用轻松自然的对话语气重写，避免学术化用语，像朋友聊天一样讲解。';
      case RewriteMode.deepThink:
        return '用户要求深度思考。请重新审视原始问题，进行多角度深入分析。'
            '考虑正反面观点、潜在风险、长期影响等，给出更有洞察力的回答。'
            '可以质疑上一次回答中的假设，并补充被遗漏的重要维度。';
    }
  }
}

class AssistantRunRequest {
  const AssistantRunRequest({
    required this.messages,
    this.sessionId,
    this.userId,
    this.profileSubjectId,
    this.subAccountId,
    this.personaContextVersion,
    this.deviceProfile = 'mobile',
    this.deviceModel = '',
    this.deviceOs = '',
    this.gpsLocation = const <String, dynamic>{},
    this.channel = 'app',
    this.traceId,
    this.maxIterations = 6,
    this.capabilityCatalog = const <String>[],
    this.contextScopeHint = const <String, dynamic>{},
    this.privacyProfile = 'default',
    this.privacyPolicy = const <String, dynamic>{},
    this.userProfileSnapshot = const <String, dynamic>{},
    this.rewriteInstruction,
  });

  final List<AssistantRunMessage> messages;
  final String? sessionId;
  final String? userId;
  final String? profileSubjectId;
  final String? subAccountId;
  final String? personaContextVersion;
  final String deviceProfile;
  final String deviceModel;
  final String deviceOs;
  final Map<String, dynamic> gpsLocation;
  final String channel;
  final String? traceId;
  final int maxIterations;
  final List<String> capabilityCatalog;
  final Map<String, dynamic> contextScopeHint;
  final String privacyProfile;
  final Map<String, dynamic> privacyPolicy;
  final Map<String, dynamic> userProfileSnapshot;
  final RewriteInstruction? rewriteInstruction;

  bool get isRewrite => rewriteInstruction != null;

  bool get shouldSkipSearch =>
      isRewrite && rewriteInstruction!.mode != RewriteMode.deepThink;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'messages': messages.map((m) => m.toJson()).toList(growable: false),
      'sessionId': sessionId,
      'userId': userId,
      'profileSubjectId': profileSubjectId,
      'subAccountId': subAccountId,
      'personaContextVersion': personaContextVersion,
      'deviceProfile': deviceProfile,
      'deviceModel': deviceModel,
      'deviceOs': deviceOs,
      'gpsLocation': gpsLocation,
      'channel': channel,
      'traceId': traceId,
      'maxIterations': maxIterations,
      'capabilityCatalog': capabilityCatalog,
      'contextScopeHint': contextScopeHint,
      'privacyProfile': privacyProfile,
      'privacyPolicy': privacyPolicy,
      'userProfileSnapshot': userProfileSnapshot,
      if (rewriteInstruction != null)
        'rewriteInstruction': rewriteInstruction!.toJson(),
    };
  }

  factory AssistantRunRequest.fromJson(Map<String, dynamic> json) {
    final rawMessages = (json['messages'] as List?) ?? const <dynamic>[];
    return AssistantRunRequest(
      messages: rawMessages
          .whereType<Map>()
          .map((m) => AssistantRunMessage.fromJson(m.cast<String, dynamic>()))
          .toList(growable: false),
      sessionId: json['sessionId'] as String?,
      userId: json['userId'] as String?,
      profileSubjectId: (json['profileSubjectId'] as String?)?.trim(),
      subAccountId: (json['subAccountId'] as String?)?.trim(),
      personaContextVersion: (json['personaContextVersion'] as String?)?.trim(),
      deviceProfile:
          (json['deviceProfile'] as String?)?.trim().isNotEmpty == true
          ? (json['deviceProfile'] as String).trim()
          : 'mobile',
      deviceModel: (json['deviceModel'] as String?)?.trim() ?? '',
      deviceOs: (json['deviceOs'] as String?)?.trim() ?? '',
      gpsLocation:
          (json['gpsLocation'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      channel: (json['channel'] as String?)?.trim().isNotEmpty == true
          ? (json['channel'] as String).trim()
          : 'app',
      traceId: (json['traceId'] as String?)?.trim(),
      maxIterations: (json['maxIterations'] as int?) ?? 6,
      capabilityCatalog:
          (json['capabilityCatalog'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      contextScopeHint:
          (json['contextScopeHint'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      privacyProfile:
          (json['privacyProfile'] as String?)?.trim().isNotEmpty == true
          ? (json['privacyProfile'] as String).trim()
          : 'default',
      privacyPolicy:
          (json['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      userProfileSnapshot:
          (json['userProfileSnapshot'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      rewriteInstruction: json['rewriteInstruction'] is Map
          ? RewriteInstruction.fromJson(
              (json['rewriteInstruction'] as Map).cast<String, dynamic>(),
            )
          : null,
    );
  }
}
