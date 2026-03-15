import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

/// 开发态排障日志：按 runId 落盘 agent loop 全链路数据。
class AssistantAgentLoopDevLogger {
  AssistantAgentLoopDevLogger._();

  static final AssistantAgentLoopDevLogger instance =
      AssistantAgentLoopDevLogger._();

  Future<String?> writeRun({
    required AssistantRunRequest request,
    required AssistantRunResponse response,
    required String sessionId,
    required String runId,
  }) async {
    if (!kDebugMode) {
      return null;
    }
    try {
      final stamp = DateTime.now();
      final interactions = AppRunInteractionCollector.instance.take(runId);
      final userMessage = request.messages.isEmpty
          ? ''
          : request.messages.last.content.trim();
      final payload = <String, dynamic>{
        'meta': <String, dynamic>{
          'generatedAt': stamp.toIso8601String(),
          'runId': runId,
          'traceId': response.traceId ?? '',
          'sessionId': sessionId,
          'channel': request.channel,
          'deviceProfile': request.deviceProfile,
          'privacyProfile': request.privacyProfile,
          'logVersion': 'v1',
        },
        'input': <String, dynamic>{
          'userMessage': userMessage,
          'messages': _safeJsonValue(
            request.messages.map((m) => m.toJson()).toList(growable: false),
          ),
          'maxIterations': request.maxIterations,
          'capabilityCatalog': request.capabilityCatalog,
          'contextScopeHint': request.contextScopeHint,
        },
        'interactions': interactions,
        'output': <String, dynamic>{
          'finalText': response.finalText,
          'degraded': response.degraded,
          'errorCode': response.errorCode,
          'traceCount': response.traces.length,
          'structuredResponse': _safeJsonValue(response.structuredResponse),
          'profileUpdateProposal': _safeJsonValue(
            response.profileUpdateProposal?.toJson(),
          ),
        },
        'response': _safeJsonMap(response.toJson()),
      };
      final path = await AppLogService.instance.writeRunFile(
        runId: runId,
        payload: payload,
      );
      if (path != null) {
        await AppLogService.instance.writeEvent(
          logType: AppLogType.agentRun,
          level: AppLogLevel.info,
          context: AppLogContext(
            sessionId: sessionId,
            runId: runId,
            traceId: response.traceId ?? '',
          ),
          payload: <String, dynamic>{
            'kind': 'agent_run',
            'runFilePath': path,
            'finalText': response.finalText,
            'interactionCount': interactions.length,
          },
          summaryPayload: <String, dynamic>{
            'kind': 'agent_run',
            'runFilePath': path,
            'interactionCount': interactions.length,
          },
        );
      }
      if (kDebugMode) {
        debugPrint('[AssistantDevLog] run log written: ${path ?? ''}');
      }
      return path;
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AssistantDevLog] write failed: $error');
      }
      return null;
    }
  }

  Map<String, dynamic> _safeJsonMap(Map<String, dynamic> source) {
    final out = <String, dynamic>{};
    source.forEach((key, value) {
      out[key] = _safeJsonValue(value);
    });
    return out;
  }

  dynamic _safeJsonValue(dynamic value) {
    if (value == null || value is num || value is String || value is bool) {
      return value;
    }
    if (value is DateTime) {
      return value.toIso8601String();
    }
    if (value is Map) {
      final safe = <String, dynamic>{};
      value.forEach((k, v) {
        safe['$k'] = _safeJsonValue(v);
      });
      return safe;
    }
    if (value is Iterable) {
      return value.map(_safeJsonValue).toList(growable: false);
    }
    return value.toString();
  }
}
