enum AppActionType {
  openConversation('open_conversation'),
  sendMessage('send_message'),
  openPost('open_post'),
  navigateToPage('navigate_to_page'),
  capturePhoto('capture_photo'),
  pickPhoto('pick_photo'),
  share('share'),
  dial('dial');

  const AppActionType(this.wireName);

  final String wireName;
}

AppActionType? parseAppActionType(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'open_conversation':
      return AppActionType.openConversation;
    case 'send_message':
      return AppActionType.sendMessage;
    case 'open_post':
      return AppActionType.openPost;
    case 'navigate_to_page':
      return AppActionType.navigateToPage;
    case 'capture_photo':
      return AppActionType.capturePhoto;
    case 'pick_photo':
      return AppActionType.pickPhoto;
    case 'share':
      return AppActionType.share;
    case 'dial':
      return AppActionType.dial;
  }
  return null;
}

enum AppActionAssessment {
  canExecuteWithTools('can_execute_with_tools'),
  searchOnlyFallback('search_only_fallback'),
  requiresUserAction('requires_user_action'),
  unsupportedAction('unsupported_action');

  const AppActionAssessment(this.wireName);

  final String wireName;
}

AppActionAssessment parseAppActionAssessment(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'search_only_fallback':
      return AppActionAssessment.searchOnlyFallback;
    case 'requires_user_action':
      return AppActionAssessment.requiresUserAction;
    case 'unsupported_action':
      return AppActionAssessment.unsupportedAction;
    default:
      return AppActionAssessment.canExecuteWithTools;
  }
}

class AppActionArgs {
  const AppActionArgs([this.fields = const <String, Object?>{}]);

  final Map<String, Object?> fields;

  Map<String, dynamic> toJson() => _normalizeObjectMap(fields);

  factory AppActionArgs.fromJson(Object? raw) {
    return AppActionArgs(_normalizeObjectMap(raw));
  }
}

class AppActionRequest {
  const AppActionRequest({
    this.contractId = 'app_action_request',
    required this.actionType,
    this.args = const AppActionArgs(),
    this.requiresConfirmation = false,
  });

  final String contractId;
  final AppActionType actionType;
  final AppActionArgs args;
  final bool requiresConfirmation;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'actionType': actionType.wireName,
    'args': args.toJson(),
    'requiresConfirmation': requiresConfirmation,
  };

  factory AppActionRequest.fromJson(Map<String, dynamic> json) {
    return AppActionRequest(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'app_action_request',
      actionType:
          parseAppActionType((json['actionType'] as String?)?.trim() ?? '') ??
          AppActionType.navigateToPage,
      args: AppActionArgs.fromJson(json['args']),
      requiresConfirmation: json['requiresConfirmation'] == true,
    );
  }
}

class AppActionResult {
  const AppActionResult({
    this.contractId = 'app_action_result',
    this.assessment = AppActionAssessment.canExecuteWithTools,
    this.executed = false,
    this.missingTool = '',
    this.missingPermission = '',
    this.suggestedAlternative = '',
    this.result = const AppActionArgs(),
  });

  final String contractId;
  final AppActionAssessment assessment;
  final bool executed;
  final String missingTool;
  final String missingPermission;
  final String suggestedAlternative;
  final AppActionArgs result;

  bool get isExecutable =>
      assessment == AppActionAssessment.canExecuteWithTools;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'assessment': assessment.wireName,
    'executed': executed,
    if (missingTool.trim().isNotEmpty) 'missingTool': missingTool.trim(),
    if (missingPermission.trim().isNotEmpty)
      'missingPermission': missingPermission.trim(),
    if (suggestedAlternative.trim().isNotEmpty)
      'suggestedAlternative': suggestedAlternative.trim(),
    'result': result.toJson(),
  };

  factory AppActionResult.fromJson(Map<String, dynamic> json) {
    return AppActionResult(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'app_action_result',
      assessment: parseAppActionAssessment(
        (json['assessment'] as String?)?.trim() ?? '',
      ),
      executed: json['executed'] == true,
      missingTool: (json['missingTool'] as String?)?.trim() ?? '',
      missingPermission: (json['missingPermission'] as String?)?.trim() ?? '',
      suggestedAlternative:
          (json['suggestedAlternative'] as String?)?.trim() ?? '',
      result: AppActionArgs.fromJson(json['result']),
    );
  }
}

Map<String, dynamic> _normalizeObjectMap(Object? raw) {
  if (raw is! Map) {
    return const <String, dynamic>{};
  }
  final normalized = <String, dynamic>{};
  raw.forEach((key, value) {
    final normalizedKey = key.toString().trim();
    if (normalizedKey.isEmpty) {
      return;
    }
    normalized[normalizedKey] = _normalizeObjectValue(value);
  });
  return normalized;
}

dynamic _normalizeObjectValue(Object? value) {
  if (value is Map) {
    return _normalizeObjectMap(value);
  }
  if (value is List) {
    return value.map<dynamic>(_normalizeObjectValue).toList(growable: false);
  }
  return value;
}
