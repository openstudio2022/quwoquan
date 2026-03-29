import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_stream_projector.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

class LocalAssistantEntry {
  const LocalAssistantEntry({
    required AssistantGateway assistantGateway,
    required AssistantRequestPolicy requestPolicy,
  }) : _assistantGateway = assistantGateway,
       _requestPolicy = requestPolicy;

  final AssistantGateway _assistantGateway;
  final AssistantRequestPolicy _requestPolicy;

  Future<AssistantRunResponse> run({
    required AssistantRunRequest request,
  }) async {
    final effectiveRequest = _requestPolicy.apply(request);
    await AssistantContentFilters.ensureLoaded();
    try {
      return await _assistantGateway.run(effectiveRequest);
    } catch (error, stackTrace) {
      return _buildErrorResponse(
        effectiveRequest,
        error,
        'local_run',
        stackTrace: stackTrace,
      );
    }
  }

  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
  }) {
    final controller = StreamController<AssistantRunStreamEvent>();
    () async {
      final effectiveRequest = _requestPolicy.apply(request);
      final toolMetadataRegistry = ToolMetadataRegistry();
      try {
        await AssistantContentFilters.ensureLoaded();
        await toolMetadataRegistry.ensureLoaded();
        final projector = AssistantStreamingProjector(
          effectiveRequest,
          toolMetadataRegistry: toolMetadataRegistry,
        );
        final response = await _assistantGateway.runWithTraceStream(
          effectiveRequest,
          onTraceEvent: (event) {
            projector.emitTrace(event, controller);
          },
        );
        final canonicalProcessTimeline = projector.resolveCompletedProcessTimeline(
          response,
        );
        if (!controller.isClosed &&
            !hasStructuredProcessTimeline(canonicalProcessTimeline)) {
          controller.add(
            AssistantRunStreamEvent.trace(
              AssistantTraceEvent(
                type: AssistantTraceEventType.lifecycleEnd,
                message: 'process timeline missing at completion',
                timestamp: DateTime.now(),
                runId: response.runId,
                traceId: response.traceId,
                visibility: TraceVisibility.system,
                data: <String, dynamic>{
                  'stage': 'process_timeline',
                  'failureCode': AssistantFailureCode.processTimelineMissing,
                },
              ),
            ),
          );
        }
        final finalizedResponse = _attachProcessTimeline(
          response,
          canonicalProcessTimeline,
        );
        if (!controller.isClosed && canonicalProcessTimeline.isNotEmpty) {
          controller.add(
            AssistantRunStreamEvent.processTimeline(
              buildVisibleProcessTimeline(canonicalProcessTimeline),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(
            AssistantRunStreamEvent.journey(
              projector.resolveCompletedJourney(finalizedResponse),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.completed(finalizedResponse));
        }
      } catch (error, stackTrace) {
        final projector = AssistantStreamingProjector(
          effectiveRequest,
          toolMetadataRegistry: toolMetadataRegistry,
        );
        final fallback = _buildErrorResponse(
          effectiveRequest,
          error,
          'local_run_stream',
          stackTrace: stackTrace,
        );
        for (final trace in fallback.traces) {
          projector.emitTrace(trace, controller);
        }
        final canonicalProcessTimeline = projector.resolveCompletedProcessTimeline(
          fallback,
        );
        if (!controller.isClosed &&
            !hasStructuredProcessTimeline(canonicalProcessTimeline)) {
          controller.add(
            AssistantRunStreamEvent.trace(
              AssistantTraceEvent(
                type: AssistantTraceEventType.lifecycleEnd,
                message: 'process timeline missing at completion',
                timestamp: DateTime.now(),
                runId: fallback.runId,
                traceId: fallback.traceId,
                visibility: TraceVisibility.system,
                data: <String, dynamic>{
                  'stage': 'process_timeline',
                  'failureCode': AssistantFailureCode.processTimelineMissing,
                },
              ),
            ),
          );
        }
        final finalizedFallback = _attachProcessTimeline(
          fallback,
          canonicalProcessTimeline,
        );
        if (!controller.isClosed && canonicalProcessTimeline.isNotEmpty) {
          controller.add(
            AssistantRunStreamEvent.processTimeline(
              buildVisibleProcessTimeline(canonicalProcessTimeline),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(
            AssistantRunStreamEvent.journey(
              projector.resolveCompletedJourney(finalizedFallback),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.completed(finalizedFallback));
        }
      } finally {
        if (!controller.isClosed) {
          await controller.close();
        }
      }
    }();
    return controller.stream;
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
  }) {
    return _assistantGateway.invokeSkill(
      skillId: skillId,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
  }

  AssistantRunResponse _buildErrorResponse(
    AssistantRunRequest request,
    Object error,
    String source, {
    StackTrace? stackTrace,
  }) {
    if (kDebugMode) {
      debugPrint('local_entry_error[$source]: ${error.runtimeType}: $error');
      if (stackTrace != null) {
        debugPrint(stackTrace.toString());
      }
    }
    return AssistantRunResponse(
      finalText: '本地助手执行异常，请重试。（$source）',
      degraded: true,
      errorCode: AssistantErrorCode.executionFailed.name,
      traces: <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message: 'local_entry_error[$source]: ${error.runtimeType}: $error',
          timestamp: DateTime.now(),
          data: <String, dynamic>{
            'source': source,
            'errorType': error.runtimeType.toString(),
            'errorMessage': error.toString(),
            if (stackTrace != null) 'stackTrace': stackTrace.toString(),
          },
        ),
      ],
      structuredResponse: <String, dynamic>{
        'qualityMetrics': <String, dynamic>{
          'decisionParseSuccess': false,
          'hardCutSource': source,
        },
      },
    );
  }

  AssistantRunResponse _attachProcessTimeline(
    AssistantRunResponse response,
    List<ProcessTimelineFrame> processTimeline,
  ) {
    final normalizedIncoming = normalizeProcessTimeline(processTimeline);
    final normalizedExisting = resolveAssistantProcessTimelineFromRunResponse(
      response,
    );
    final normalizedPreferred =
        hasStructuredProcessTimeline(normalizedIncoming) &&
            normalizedIncoming.length >= normalizedExisting.length
        ? normalizedIncoming
        : normalizedExisting;
    if (!hasStructuredProcessTimeline(normalizedPreferred)) {
      return response;
    }
    final structured = <String, dynamic>{...response.structuredResponse};
    final rawRunArtifacts =
        (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final encodedTimeline = normalizedPreferred
        .map((item) => item.toJson())
        .toList(growable: false);
    structured['processTimeline'] = encodedTimeline;
    structured['runArtifacts'] = <String, dynamic>{
      ...rawRunArtifacts,
      'processTimeline': encodedTimeline,
    };
    return AssistantRunResponse(
      finalText: response.finalText,
      traces: response.traces,
      runId: response.runId,
      traceId: response.traceId,
      degraded: response.degraded,
      errorCode: response.errorCode,
      structuredResponse: structured,
      profileUpdateProposal: response.profileUpdateProposal,
    );
  }
}
