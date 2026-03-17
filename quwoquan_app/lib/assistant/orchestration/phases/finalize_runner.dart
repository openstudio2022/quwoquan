import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

typedef ObservabilityPayloadBuilder =
    Map<String, dynamic> Function({
      required AssistantRunResponse response,
      required AssistantRunRequest request,
    });

class FinalizeRunner {
  const FinalizeRunner({
    required this.sessionManager,
    required this.memoryRepository,
    required this.buildObservabilityPayload,
  });

  final AssistantSessionManager sessionManager;
  final AssistantMemoryRepository memoryRepository;
  final ObservabilityPayloadBuilder buildObservabilityPayload;

  Future<AssistantRunResponse> finalize(
    AssistantRunRequest request, {
    required Map<String, dynamic> executionSnapshot,
    required AssistantRunResponse response,
  }) async {
    final sessionId =
        (executionSnapshot['sessionId'] as String?) ??
        (request.sessionId ?? 'default');
    final latestUserQuery =
        (executionSnapshot['latestUserQuery'] as String?)?.trim() ?? '';
    final runStartAt = executionSnapshot['runStartAt'] as DateTime?;
    final runId =
        response.runId ??
        (executionSnapshot['runId'] as String?) ??
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final traceId =
        response.traceId ??
        (executionSnapshot['traceId'] as String?) ??
        request.traceId ??
        runId;
    final completedArtifact = response.runArtifacts;
    if (completedArtifact == null) {
      return response;
    }
    final displayMarkdown = completedArtifact.displayMarkdown.trim();
    final displayPlainText = completedArtifact.displayPlainText.trim();
    final displayTextForSession = displayMarkdown.isNotEmpty
        ? displayMarkdown
        : displayPlainText;
    final isDegradedReply =
        response.degraded ||
        AssistantContentFilters.isDegradedText(response.finalText);
    sessionManager.updateSessionTopicSummary(
      sessionId: sessionId,
      latestUserQuery: latestUserQuery,
      latestAssistantReply: displayPlainText.isNotEmpty
          ? displayPlainText
          : displayTextForSession,
    );
    if (displayPlainText.isNotEmpty) {
      await memoryRepository.rememberText(
        id: '${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: displayPlainText,
        metadata: <String, dynamic>{
          'sessionId': sessionId,
          'userId': request.userId ?? '',
          'deviceProfile': request.deviceProfile,
          'deviceModel': request.deviceModel,
          'deviceOs': request.deviceOs,
        },
      );
    }
    if (!isDegradedReply && displayTextForSession.isNotEmpty) {
      final structuredResponse = response.structuredResponse;
      sessionManager.appendMessage(
        sessionId: sessionId,
        role: 'assistant',
        content: displayTextForSession,
        metadata: <String, dynamic>{
          'displayMarkdown': displayMarkdown,
          'displayPlainText': displayPlainText,
          'machineEnvelope': completedArtifact.machineEnvelope,
          'runArtifacts': completedArtifact.toJson(),
          'uiProcessContentBlocks':
              (structuredResponse['uiProcessContentBlocks'] as List?) ??
              const <dynamic>[],
          'uiProcessTimeline':
              (structuredResponse['uiProcessTimeline'] as List?) ??
              (structuredResponse['uiProcessTimelineV2'] as List?) ??
              const <dynamic>[],
          'uiUsageStats':
              ((structuredResponse['uiUsageStats'] as Map?) ??
                  (structuredResponse['uiUsageStatsV1'] as Map?)) ??
              const <String, dynamic>{},
          'intentGraph':
              (structuredResponse['intentGraph'] as Map?) ??
              const <String, dynamic>{},
          'skillRuns':
              (structuredResponse['skillRuns'] as List?) ?? const <dynamic>[],
          'aggregationState':
              (structuredResponse['aggregationState'] as Map?) ??
              const <String, dynamic>{},
        },
      );
    }
    await sessionManager.save();
    await _persistLearningTags(
      response: response,
      sessionId: sessionId,
      userId: request.userId ?? '',
    );
    await AssistantAgentLoopDevLogger.instance.writeRun(
      request: request,
      response: response,
      sessionId: sessionId,
      runId: runId,
    );
    await _safeWriteLogEvent(
      logType: AppLogType.agentRun,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: buildObservabilityPayload(response: response, request: request),
      summaryPayload: <String, dynamic>{
        'kind': 'agent_run',
        'runId': runId,
        'traceId': traceId,
        'degraded': response.degraded,
      },
      hasError: response.degraded,
    );
    final runLatencyMs = runStartAt == null
        ? 0
        : DateTime.now().difference(runStartAt).inMilliseconds;
    await _safeWriteLogEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: AppPerfProbe.snapshot(
        event: 'operation',
        route: '/assistant/run',
        operation: 'agent_run_end',
        latencyMs: runLatencyMs,
      ),
      summaryPayload: <String, dynamic>{
        'event': 'operation',
        'operation': 'agent_run_end',
        'latencyMs': runLatencyMs,
      },
    );
    return response;
  }

  Future<void> _persistLearningTags({
    required AssistantRunResponse response,
    required String sessionId,
    required String userId,
  }) async {
    try {
      final structured = response.structuredResponse;
      final learningTrack =
          (structured['learningTrack'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final tags =
          (learningTrack['profileTagDelta'] as List?)
              ?.whereType<Map>()
              .map((t) => t.cast<String, dynamic>())
              .where((t) => (t['tag'] ?? '').toString().isNotEmpty)
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (tags.isEmpty) return;

      final tagSummary = tags
          .map((t) => '${t['tag']}: ${t['value'] ?? t['confidence'] ?? ''}')
          .join('; ');
      await memoryRepository.rememberText(
        id: 'learning_${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: '用户画像标签: $tagSummary',
        metadata: <String, dynamic>{
          'type': 'learning_tag',
          'sessionId': sessionId,
          'userId': userId,
          'tags': tags,
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    } catch (_) {
      // Non-critical: silently ignore persistence failures.
    }
  }

  Future<void> _safeWriteLogEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required AppLogContext context,
    required dynamic payload,
    required Map<String, dynamic> summaryPayload,
    bool hasError = false,
  }) async {
    try {
      await AppLogService.instance.writeEvent(
        logType: logType,
        level: level,
        context: context,
        payload: payload,
        summaryPayload: summaryPayload,
        hasError: hasError,
      );
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[FinalizeRunner] log write skipped: $error');
      }
    }
  }
}
