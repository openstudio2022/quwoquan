// ASSISTANT_WEAK_TYPE: LLM_RAW | EXTENSION_MAP — 远端流式与 RunArtifacts 投影；边界后使用 codegen 类型。

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_stream_projector.dart';
import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

class RemoteAssistantEntry {
  const RemoteAssistantEntry({
    required OpenClawBridge openClawBridge,
    required AssistantRequestPolicy requestPolicy,
  }) : _openClawBridge = openClawBridge,
       _requestPolicy = requestPolicy;

  final OpenClawBridge _openClawBridge;
  final AssistantRequestPolicy _requestPolicy;

  Future<AssistantRunResponse> run({
    required AssistantRunRequest request,
  }) async {
    final effectiveRequest = _requestPolicy.apply(request);
    await AssistantContentFilters.ensureLoaded();
    try {
      final remote = await _openClawBridge.runRemote(effectiveRequest);
      if (remote != null) {
        return _normalizeCompletedResponse(remote);
      }
      return _buildErrorResponse(
        effectiveRequest,
        'remote gateway unavailable',
        'remote_run_unavailable',
      );
    } catch (error, stackTrace) {
      return _buildErrorResponse(
        effectiveRequest,
        error,
        'remote_run',
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
      AssistantRunResponse? completed;
      var streamedAnswer = '';
      var visibleStreamedAnswer = '';
      final streamingAnswerDecoder = AssistantStreamingAnswerDecoder();
      try {
        await AssistantContentFilters.ensureLoaded();
        await toolMetadataRegistry.ensureLoaded();
        final projector = AssistantStreamingProjector(
          effectiveRequest,
          toolMetadataRegistry: toolMetadataRegistry,
        );
        await for (final event in _openClawBridge.runRemoteStream(
          effectiveRequest,
        )) {
          switch (event.type) {
            case OpenClawRemoteStreamEventType.chunk:
              if ((event.chunkText?.isNotEmpty ?? false)) {
                streamedAnswer = _mergeStreamedAnswer(
                  streamedAnswer,
                  event.chunkText!,
                );
                visibleStreamedAnswer = _mergeStreamedAnswer(
                  visibleStreamedAnswer,
                  streamingAnswerDecoder.appendChunk(event.chunkText!),
                );
                projector.emitRemoteChunk(event.chunkText!, controller);
              }
              break;
            case OpenClawRemoteStreamEventType.trace:
              if (event.trace != null) {
                final traceDelta = _traceAnswerDelta(event.trace!);
                streamedAnswer = _mergeStreamedAnswer(
                  streamedAnswer,
                  traceDelta,
                );
                visibleStreamedAnswer = _mergeStreamedAnswer(
                  visibleStreamedAnswer,
                  streamingAnswerDecoder.appendChunk(traceDelta),
                );
                projector.emitTrace(event.trace!, controller);
              }
              break;
            case OpenClawRemoteStreamEventType.userEvent:
              if (event.userEvent != null) {
                final userEventDelta = _userEventAnswerDelta(event.userEvent!);
                streamedAnswer = _mergeStreamedAnswer(
                  streamedAnswer,
                  userEventDelta,
                );
                visibleStreamedAnswer = _mergeStreamedAnswer(
                  visibleStreamedAnswer,
                  streamingAnswerDecoder.appendChunk(userEventDelta),
                );
                projector.emitUserEvent(event.userEvent!, controller);
              }
              break;
            case OpenClawRemoteStreamEventType.completed:
              completed = event.response;
              break;
            case OpenClawRemoteStreamEventType.failed:
              completed = _buildErrorResponse(
                effectiveRequest,
                event.errorMessage ?? 'remote stream failed',
                'remote_stream_failed',
              );
              break;
          }
          if (completed != null) {
            break;
          }
        }
        completed ??= _buildSynthesizedCompletedResponse(
          effectiveRequest,
          rawStreamedAnswer: streamedAnswer,
          visibleStreamedAnswer: visibleStreamedAnswer,
        );
        completed ??= await _openClawBridge.runRemote(effectiveRequest);
        completed ??= _buildErrorResponse(
          effectiveRequest,
          'remote stream ended without completed payload',
          'remote_stream_incomplete',
        );
        final resolvedResponse = _normalizeCompletedResponse(completed);
        final resolvedJourney = projector.resolveCompletedJourney(
          resolvedResponse,
        );
        final canonicalProcessTimeline = projector.resolveCompletedProcessTimeline(
          resolvedResponse,
        );
        if (!controller.isClosed &&
            !hasStructuredProcessTimeline(canonicalProcessTimeline)) {
          controller.add(
            AssistantRunStreamEvent.trace(
              AssistantTraceEvent(
                type: AssistantTraceEventType.lifecycleEnd,
                message: 'process timeline missing at completion',
                timestamp: DateTime.now(),
                runId: resolvedResponse.runId,
                traceId: resolvedResponse.traceId,
                visibility: TraceVisibility.system,
                data: <String, dynamic>{
                  'stage': 'process_timeline',
                  'failureCode': AssistantFailureCode.processTimelineMissing,
                },
              ),
            ),
          );
        }
        final finalizedResponse = _attachJourney(
          _attachProcessTimeline(resolvedResponse, canonicalProcessTimeline),
          resolvedJourney,
        );
        if (!controller.isClosed && canonicalProcessTimeline.isNotEmpty) {
          controller.add(
            AssistantRunStreamEvent.processTimeline(
              buildVisibleProcessTimeline(canonicalProcessTimeline),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.journey(resolvedJourney));
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
          'remote_run_stream',
          stackTrace: stackTrace,
        );
        final resolvedJourney = projector.resolveCompletedJourney(fallback);
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
        final finalizedFallback = _attachJourney(
          _attachProcessTimeline(fallback, canonicalProcessTimeline),
          resolvedJourney,
        );
        if (!controller.isClosed && canonicalProcessTimeline.isNotEmpty) {
          controller.add(
            AssistantRunStreamEvent.processTimeline(
              buildVisibleProcessTimeline(canonicalProcessTimeline),
            ),
          );
        }
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.journey(resolvedJourney));
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

  AssistantRunResponse? _buildSynthesizedCompletedResponse(
    AssistantRunRequest request, {
    required String rawStreamedAnswer,
    required String visibleStreamedAnswer,
  }) {
    final markdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          visibleStreamedAnswer,
          allowJsonExtraction: true,
        );
    final plain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          visibleStreamedAnswer,
          allowJsonExtraction: true,
        );
    final finalText = plain.isNotEmpty
        ? plain
        : AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
            markdown,
            allowJsonExtraction: false,
          );
    if (finalText.isEmpty) {
      return null;
    }
    return AssistantRunResponse(
      finalText: finalText,
      traces: <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleEnd,
          message:
              'remote stream completed without terminal payload; keep streamed answer as degraded incomplete output',
          timestamp: DateTime.now(),
          runId: request.traceId,
          traceId: request.traceId,
          data: <String, dynamic>{
            'source': 'remote_stream_terminal_payload_missing',
            'terminalPayloadComplete': false,
            'streamedAnswerLength': finalText.length,
            'rawStreamedAnswerLength': rawStreamedAnswer.length,
            'visibleStreamedAnswerLength': visibleStreamedAnswer.length,
          },
        ),
      ],
      runId: request.traceId,
      traceId: request.traceId,
      degraded: true,
      errorCode: 'remote_stream_terminal_payload_missing',
      structuredResponse: <String, dynamic>{
        'qualityMetrics': <String, dynamic>{
          'decisionParseSuccess': false,
          'hardCutSource': 'remote_stream_terminal_payload_missing',
          'remoteStreamSynthesized': true,
          'answerGateReady': false,
          'answerGateReasonCode': 'missing_terminal_payload',
        },
        'runArtifacts': <String, dynamic>{
          'displayMarkdown': markdown.isNotEmpty ? markdown : finalText,
          'displayPlainText': plain.isNotEmpty ? plain : finalText,
        },
      },
    );
  }

  String _traceAnswerDelta(AssistantTraceEvent trace) {
    if (trace.type != AssistantTraceEventType.answerDelta &&
        trace.type != AssistantTraceEventType.streamDelta) {
      return '';
    }
    return ((trace.data?['delta'] as String?) ?? trace.message).trim();
  }

  String _userEventAnswerDelta(UserEvent event) {
    if (event.type != UserEventType.answerDelta) {
      return '';
    }
    return event.message.trim();
  }

  String _mergeStreamedAnswer(String current, String next) {
    final incoming = next.trim();
    if (incoming.isEmpty) {
      return current;
    }
    final existing = current;
    if (existing.isEmpty) {
      return incoming;
    }
    if (existing == incoming || existing.endsWith(incoming)) {
      return existing;
    }
    if (incoming.startsWith(existing)) {
      return incoming;
    }
    final maxOverlap = existing.length < incoming.length
        ? existing.length
        : incoming.length;
    for (var size = maxOverlap; size > 0; size--) {
      if (existing.substring(existing.length - size) ==
          incoming.substring(0, size)) {
        return '$existing${incoming.substring(size)}';
      }
    }
    return '$existing$incoming';
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
  }) async {
    final result = await _openClawBridge.invokeSkillRemote(
      skillId: skillId,
      arguments: arguments,
    );
    if (result == null) {
      return const AssistantToolResult(
        success: false,
        message: '远端技能调用不可用',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
      );
    }
    return AssistantToolResult.fromJson(result.cast<String, dynamic>());
  }

  AssistantRunResponse _buildErrorResponse(
    AssistantRunRequest request,
    Object error,
    String source, {
    StackTrace? stackTrace,
  }) {
    if (kDebugMode) {
      debugPrint('remote_entry_error[$source]: ${error.runtimeType}: $error');
      if (stackTrace != null) {
        debugPrint(stackTrace.toString());
      }
    }
    return _ensureCanonicalGate(
      AssistantRunResponse(
      finalText: '远端助手执行异常，请重试。（$source）',
      degraded: true,
      errorCode: 'remote_entry_failure',
      traces: <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message: 'remote_entry_error[$source]: ${error.runtimeType}: $error',
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
      ),
      reasonCode: 'degraded_response',
      reason: '远端助手当前未形成稳定终态，先不按成功完成处理。',
    );
  }

  AssistantRunResponse _attachJourney(
    AssistantRunResponse response,
    AssistantJourney journey,
  ) {
    if (journey.isEmpty) return response;
    final existingJourney = response.runArtifacts?.journey;
    if (existingJourney != null && !existingJourney.isEmpty) {
      return response;
    }
    final structured = <String, dynamic>{...response.structuredResponse};
    final rawRunArtifacts =
        (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    structured['journey'] = journey.toJson();
    structured['runArtifacts'] = <String, dynamic>{
      ...rawRunArtifacts,
      'journey': journey.toJson(),
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

  AssistantRunResponse _normalizeCompletedResponse(
    AssistantRunResponse response,
  ) {
    final structured = <String, dynamic>{...response.structuredResponse};
    final rawRunArtifacts =
        (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final normalizedMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          (rawRunArtifacts['displayMarkdown'] as String?)?.trim().isNotEmpty ==
                  true
              ? (rawRunArtifacts['displayMarkdown'] as String)
              : ((structured['userMarkdown'] as String?)?.trim().isNotEmpty ==
                      true
                  ? (structured['userMarkdown'] as String)
                  : response.finalText),
        );
    if (normalizedMarkdown.isEmpty) {
      return response;
    }
    final normalizedPlainText = AssistantDisplayTextResolver.stripMarkdown(
      normalizedMarkdown,
    ).trim();
    structured['runArtifacts'] = <String, dynamic>{
      ...rawRunArtifacts,
      'displayMarkdown': normalizedMarkdown,
      'displayPlainText': normalizedPlainText.isNotEmpty
          ? normalizedPlainText
          : ((rawRunArtifacts['displayPlainText'] as String?)?.trim() ??
                response.finalText),
    };
    final normalizedResponse = AssistantRunResponse(
      finalText: response.finalText,
      traces: response.traces,
      runId: response.runId,
      traceId: response.traceId,
      degraded: response.degraded,
      errorCode: response.errorCode,
      structuredResponse: structured,
      profileUpdateProposal: response.profileUpdateProposal,
    );
    if (response.degraded) {
      return _ensureCanonicalGate(
        normalizedResponse,
        reasonCode: response.errorCode == 'remote_stream_terminal_payload_missing'
            ? 'missing_terminal_payload'
            : 'degraded_response',
        reason: response.errorCode == 'remote_stream_terminal_payload_missing'
            ? '远端流式结果缺少终态 payload，当前只保留可见增量，不按成功完成处理。'
            : '远端结果处于降级态，当前不按成功完成处理。',
        terminalPayloadComplete:
            response.errorCode != 'remote_stream_terminal_payload_missing',
      );
    }
    return normalizedResponse;
  }

  AssistantRunResponse _ensureCanonicalGate(
    AssistantRunResponse response, {
    required String reasonCode,
    required String reason,
    bool terminalPayloadComplete = false,
  }) {
    final structured = <String, dynamic>{...response.structuredResponse};
    if (structured[assistantAnswerGateDecisionField] is Map &&
        structured[assistantRetrievalOutcomeField] is Map) {
      return response;
    }
    final rawRunArtifacts =
        (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final rawAnswerDecision =
        (rawRunArtifacts['answerDecision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final hasRenderableAnswer =
        ((rawRunArtifacts['displayMarkdown'] as String?)?.trim().isNotEmpty ==
            true) ||
        ((rawRunArtifacts['displayPlainText'] as String?)?.trim().isNotEmpty ==
            true);
    structured[assistantAnswerGateDecisionField] = <String, dynamic>{
      'eligible': false,
      'finalAnswerReady': false,
      'reasonCode': reasonCode,
      'reason': reason,
      'nextAction': 'abort',
      'answerEligibility': 'blocked',
      'renderable': hasRenderableAnswer,
      'retrievalReady': false,
      'terminalPayloadComplete': terminalPayloadComplete,
      'degraded': true,
      'incomplete': !terminalPayloadComplete,
    };
    structured[assistantRetrievalOutcomeField] = <String, dynamic>{
      'status': terminalPayloadComplete ? 'degraded' : 'incomplete',
      'summary': reason,
      'terminalPayloadComplete': terminalPayloadComplete,
      'degraded': true,
      'retrievalProcessing':
          (rawRunArtifacts['retrievalProcessing'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    };
    structured['conversationStateDecision'] = <String, dynamic>{
      'nextAction': 'abort',
      'answerEligibility': 'blocked',
      'finalAnswerReady': false,
    };
    structured['qualityMetrics'] = <String, dynamic>{
      ...((structured['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{}),
      'answerGateReady': false,
      'answerGateReasonCode': reasonCode,
      'hardCutSource':
          ((structured['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{})['hardCutSource'] ??
          response.errorCode ??
          reasonCode,
    };
    structured['runArtifacts'] = <String, dynamic>{
      ...rawRunArtifacts,
      'answerDecision': <String, dynamic>{
        ...rawAnswerDecision,
        'nextAction': 'abort',
        'answerEligibility': 'blocked',
        'finalAnswerReady': false,
        'reasonCode': reasonCode,
        'reason': reason,
        'terminalPayloadComplete': terminalPayloadComplete,
      },
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
