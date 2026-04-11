import 'package:quwoquan_app/assistant/observability/assistant_observability_runtime.dart';

List<Object?> _assistantGatewayJsonList(Object? value) =>
    value is List ? value : const <Object?>[];

/// JSON body for `POST /v1/assistant/models/select` (local operator API).
class AssistantGatewayModelSelectBody {
  const AssistantGatewayModelSelectBody({
    required this.selectedModels,
    required this.modelRef,
  });

  final List<String> selectedModels;
  final String modelRef;

  factory AssistantGatewayModelSelectBody.fromJson(Map<String, dynamic> json) {
    final selectedModels = _assistantGatewayJsonList(json['selectedModels'])
            .whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
    final modelRef = (json['modelRef'] as String?)?.trim() ?? '';
    return AssistantGatewayModelSelectBody(
      selectedModels: selectedModels,
      modelRef: modelRef,
    );
  }
}

/// JSON body for `POST /v1/assistant/logs/export`.
class AssistantGatewayLogsExportBody {
  const AssistantGatewayLogsExportBody({required this.targetDirectory});

  /// Default matches historical gateway behavior when field omitted.
  static const String kDefaultTargetDirectory =
      '/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log';

  final String targetDirectory;

  factory AssistantGatewayLogsExportBody.fromJson(Map<String, dynamic> json) {
    final raw = (json['targetDirectory'] as String?)?.trim() ?? '';
    return AssistantGatewayLogsExportBody(
      targetDirectory: raw.isNotEmpty ? raw : kDefaultTargetDirectory,
    );
  }
}

/// JSON body for `POST /v1/assistant/logs/boost`.
class AssistantGatewayLogsBoostBody {
  const AssistantGatewayLogsBoostBody({
    required this.sessionId,
    required this.runId,
    required this.clear,
  });

  final String sessionId;
  final String runId;
  final bool clear;

  factory AssistantGatewayLogsBoostBody.fromJson(Map<String, dynamic> json) {
    return AssistantGatewayLogsBoostBody(
      sessionId: (json['sessionId'] as String?)?.trim() ?? '',
      runId: (json['runId'] as String?)?.trim() ?? '',
      clear: json['clear'] == true,
    );
  }
}

/// JSON body for `POST /v1/assistant/alerts/test`.
class AssistantGatewayAlertsTestBody {
  const AssistantGatewayAlertsTestBody({
    required this.severity,
    required this.providerId,
    required this.message,
  });

  final AssistantSloAlertSeverity severity;
  final String providerId;
  final String message;

  factory AssistantGatewayAlertsTestBody.fromJson(Map<String, dynamic> json) {
    final severityRaw =
        (json['severity'] as String?)?.trim().toLowerCase() ?? 'warning';
    final severity = severityRaw == 'critical'
        ? AssistantSloAlertSeverity.critical
        : AssistantSloAlertSeverity.warning;
    final providerIdRaw = (json['providerId'] as String?)?.trim() ?? '';
    final providerId = providerIdRaw.isNotEmpty
        ? providerIdRaw
        : 'synthetic_provider';
    final messageRaw = (json['message'] as String?)?.trim() ?? '';
    final message = messageRaw.isNotEmpty
        ? messageRaw
        : 'synthetic alert for routing verification';
    return AssistantGatewayAlertsTestBody(
      severity: severity,
      providerId: providerId,
      message: message,
    );
  }
}

/// JSON body for `POST .../skills/invoke` (assistant API + slim HTTP gateway).
class AssistantGatewaySkillInvokeBody {
  const AssistantGatewaySkillInvokeBody({
    required this.skillId,
    required this.actorUserId,
    required this.channel,
    required this.arguments,
    required this.deviceProfile,
    this.traceId,
  });

  final String skillId;
  final String actorUserId;
  final String channel;
  final Map<String, dynamic> arguments;
  final String deviceProfile;
  final String? traceId;

  factory AssistantGatewaySkillInvokeBody.fromJson(Map<String, dynamic> json) {
    return AssistantGatewaySkillInvokeBody(
      skillId: (json['skill_id'] as String?)?.trim() ?? '',
      actorUserId: (json['userId'] as String?)?.trim() ?? 'external',
      channel: (json['channel'] as String?)?.trim() ?? 'app',
      arguments:
          (json['arguments'] as Map?)?.cast<String, dynamic>() ??
          <String, dynamic>{},
      deviceProfile: (json['deviceProfile'] as String?)?.trim() ?? 'mobile',
      traceId: (json['traceId'] as String?)?.trim(),
    );
  }
}

/// Model routing hints sent alongside run body (`modelRef`, `selectedModels`).
class AssistantGatewayRunModelHintsBody {
  const AssistantGatewayRunModelHintsBody({
    required this.modelRef,
    required this.selectedModels,
  });

  final String modelRef;
  final List<String> selectedModels;

  factory AssistantGatewayRunModelHintsBody.fromJson(
    Map<String, dynamic> json,
  ) {
    final selectedModels = _assistantGatewayJsonList(json['selectedModels'])
            .whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
    return AssistantGatewayRunModelHintsBody(
      modelRef: (json['modelRef'] as String?)?.trim() ?? '',
      selectedModels: selectedModels,
    );
  }
}
