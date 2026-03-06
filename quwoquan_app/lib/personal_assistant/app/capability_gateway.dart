import 'dart:async';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_response_parser.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

enum CapabilityRouteMode { localOnly, remotePreferred, hybrid }

enum AssistantRunStreamEventType {
  trace,
  chunk,
  completed,
  failed,
  // v2 semantic event types
  planStarted,
  searchProgress,
  thinkingProgress,
  answerDelta,
  phaseTimeline,
  // v3 user-facing phase events
  userPhaseEvent,
}

class AssistantRunStreamEvent {
  const AssistantRunStreamEvent._({
    required this.type,
    this.trace,
    this.chunkText,
    this.response,
    this.errorMessage,
  });

  factory AssistantRunStreamEvent.trace(AssistantTraceEvent trace) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.trace,
        trace: trace,
      );

  factory AssistantRunStreamEvent.chunk(String chunkText) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.chunk,
        chunkText: chunkText,
      );

  factory AssistantRunStreamEvent.completed(AssistantRunResponse response) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.completed,
        response: response,
      );

  factory AssistantRunStreamEvent.failed(String errorMessage) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.failed,
        errorMessage: errorMessage,
      );

  factory AssistantRunStreamEvent.planStarted({String? planSummary}) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.planStarted,
        chunkText: planSummary,
      );

  factory AssistantRunStreamEvent.searchProgress(String detail) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.searchProgress,
        chunkText: detail,
      );

  factory AssistantRunStreamEvent.thinkingProgress(String detail) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.thinkingProgress,
        chunkText: detail,
      );

  factory AssistantRunStreamEvent.answerDelta(String delta) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.answerDelta,
        chunkText: delta,
      );

  factory AssistantRunStreamEvent.phaseTimeline(
    List<Map<String, dynamic>> phases,
  ) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.phaseTimeline,
        trace: AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleEnd,
          message: 'phase_timeline',
          timestamp: DateTime.now(),
          data: <String, dynamic>{'phases': phases},
        ),
      );

  factory AssistantRunStreamEvent.userPhase({
    required UserPhaseEventType phaseType,
    String? toolName,
    String? message,
    Map<String, dynamic>? data,
  }) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.userPhaseEvent,
        trace: AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleStart,
          message: message ?? phaseType.name,
          timestamp: DateTime.now(),
          data: <String, dynamic>{
            'userPhaseType': phaseType.name,
            if (toolName != null) 'toolName': toolName,
            ...?data,
          },
        ),
        chunkText: message,
      );

  final AssistantRunStreamEventType type;
  final AssistantTraceEvent? trace;
  final String? chunkText;
  final AssistantRunResponse? response;
  final String? errorMessage;

  /// For userPhaseEvent type, returns the [UserPhaseEventType].
  UserPhaseEventType? get userPhaseType {
    if (type != AssistantRunStreamEventType.userPhaseEvent) return null;
    final name = trace?.data?['userPhaseType'] as String?;
    if (name == null) return null;
    return UserPhaseEventType.values.firstWhere(
      (e) => e.name == name,
      orElse: () => UserPhaseEventType.understandingStarted,
    );
  }

  /// For userPhaseEvent type, returns the associated tool name.
  String? get userPhaseToolName {
    return trace?.data?['toolName'] as String?;
  }
}

class CapabilityGateway {
  CapabilityGateway({
    required AssistantGateway assistantGateway,
    required OpenClawBridge openClawBridge,
  }) : _assistantGateway = assistantGateway,
       _openClawBridge = openClawBridge {
    _openClawBridge.bindLocalGateway(assistantGateway);
  }

  final AssistantGateway _assistantGateway;
  final OpenClawBridge _openClawBridge;

  bool _isRemoteResponseCommercialReady(AssistantRunResponse response) {
    if (response.degraded) return false;
    final structured = response.structuredResponse;
    final dialogueRuntime =
        (structured['dialogueRuntime'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final domainId = (dialogueRuntime['domainId'] as String?)?.trim() ?? '';
    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdown = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    final hasRawTraceLikePrefix = RegExp(
      r'^\s*\[(page|memory|tool|trace)\.',
      caseSensitive: false,
    ).hasMatch(response.finalText);
    return domainId.isNotEmpty && markdown.isNotEmpty && !hasRawTraceLikePrefix;
  }

  Future<AssistantRunResponse> run({
    required AssistantRunRequest request,
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) async {
    await AssistantContentFilters.ensureLoaded();
    if (mode == CapabilityRouteMode.localOnly) {
      return _safeLocalRun(request);
    }
    if (mode == CapabilityRouteMode.remotePreferred) {
      final remote = await _safeRemoteRun(request);
      if (remote != null && _isRemoteResponseCommercialReady(remote)) {
        return remote;
      }
      return _safeLocalRun(request);
    }
    final local = await _safeLocalRun(request);
    if (local.degraded) {
      final remote = await _safeRemoteRun(request);
      if (remote != null && _isRemoteResponseCommercialReady(remote)) {
        return remote;
      }
    }
    return local;
  }

  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) {
    final controller = StreamController<AssistantRunStreamEvent>();
    () async {
      try {
        await AssistantContentFilters.ensureLoaded();
        if (mode == CapabilityRouteMode.localOnly) {
          final local = await _runLocalWithStream(request, controller);
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        if (mode == CapabilityRouteMode.remotePreferred) {
          final remote = await _runRemoteWithStream(request, controller);
          if (remote != null && _isRemoteResponseCommercialReady(remote)) {
            controller.add(AssistantRunStreamEvent.completed(remote));
            return;
          }
          // Remote 不满足要求时，清除已累积的 streamFinalAnswer（发送一个空 chunk 标记重置）
          // 然后走 local，但 local 此时只取 completed，不发 chunk，避免两路叠加
          controller.add(AssistantRunStreamEvent.chunk(''));
          final local = await _runLocalWithStreamSilent(request, controller);
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final local = await _runLocalWithStream(request, controller);
        if (!local.degraded) {
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final remote = await _safeRemoteRun(request);
        if (remote != null && _isRemoteResponseCommercialReady(remote)) {
          for (final trace in remote.traces) {
            controller.add(AssistantRunStreamEvent.trace(trace));
          }
          controller.add(AssistantRunStreamEvent.completed(remote));
        } else {
          controller.add(AssistantRunStreamEvent.completed(local));
        }
      } catch (error) {
        // 绝不发 failed 事件：任何异常都转为 completed + degraded response，
        // 保证 UI 层永远能收到 completed 事件并提取 finalText。
        controller.add(AssistantRunStreamEvent.completed(
          _buildGatewayErrorResponse(request, error, 'runstream_outer'),
        ));
      } finally {
        if (!controller.isClosed) {
          await controller.close();
        }
      }
    }();
    return controller.stream;
  }

  Future<AssistantRunResponse> _safeLocalRun(
    AssistantRunRequest request,
  ) async {
    try {
      return await _assistantGateway.run(request);
    } catch (error) {
      // agentLoop.run() 已加外层 try-catch，正常路径不会到此。
      // 此处捕获的是 gateway 初始化或调度层面的意外异常。
      return _buildGatewayErrorResponse(request, error, 'safe_local_run');
    }
  }

  Future<AssistantRunResponse> _runLocalWithStream(
    AssistantRunRequest request,
    StreamController<AssistantRunStreamEvent> controller,
  ) async {
    try {
      final response = await _assistantGateway.runWithTraceStream(
        request,
        onTraceEvent: (event) {
          if (controller.isClosed) return;
          controller.add(AssistantRunStreamEvent.trace(event));
          // v2: emit semantic events based on trace type for granular UI
          _emitSemanticEvent(event, controller);
        },
      );
      // v2: emit phase timeline from structured response
      final phases = (response.structuredResponse['uiPhaseTimelineV1'] as List?)
          ?.whereType<Map<String, dynamic>>()
          .toList(growable: false);
      if (phases != null && phases.isNotEmpty && !controller.isClosed) {
        controller.add(AssistantRunStreamEvent.phaseTimeline(phases));
      }
      final chunkText = _resolveChunkDisplayText(response);
      if (chunkText.isNotEmpty && !controller.isClosed) {
        for (final chunk in _chunkText(chunkText)) {
          if (chunk.trim().isEmpty) continue;
          controller.add(AssistantRunStreamEvent.chunk(chunk));
        }
      }
      return response;
    } catch (error) {
      final fallback = _buildGatewayErrorResponse(
        request,
        error,
        'local_with_stream',
      );
      for (final trace in fallback.traces) {
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.trace(trace));
        }
      }
      return fallback;
    }
  }

  /// 静默运行本地网关：只发 trace 事件，不发 chunk。
  /// 用于 remote 失败 fallback 到 local 的场景，避免 chunk 两路叠加。
  Future<AssistantRunResponse> _runLocalWithStreamSilent(
    AssistantRunRequest request,
    StreamController<AssistantRunStreamEvent> controller,
  ) async {
    try {
      final response = await _assistantGateway.runWithTraceStream(
        request,
        onTraceEvent: (event) {
          if (!controller.isClosed) {
            controller.add(AssistantRunStreamEvent.trace(event));
          }
        },
      );
      return response;
    } catch (error) {
      final fallback = _buildGatewayErrorResponse(
        request,
        error,
        'local_with_stream_silent',
      );
      for (final trace in fallback.traces) {
        if (!controller.isClosed) {
          controller.add(AssistantRunStreamEvent.trace(trace));
        }
      }
      return fallback;
    }
  }

  AssistantRunResponse _buildGatewayErrorResponse(
    AssistantRunRequest request,
    Object error,
    String source,
  ) {
    return AssistantRunResponse(
      finalText: '助手服务出现异常，请重试。（$source）',
      degraded: true,
      errorCode: AssistantErrorCode.executionFailed.name,
      traces: <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message: 'gateway_error[$source]: ${error.runtimeType}: $error',
          timestamp: DateTime.now(),
          data: <String, dynamic>{
            'source': source,
            'errorType': error.runtimeType.toString(),
          },
        ),
      ],
    );
  }

  String _resolveChunkDisplayText(AssistantRunResponse response) {
    final structured = response.structuredResponse;

    // Gate 1: 结构化信号排除非最终答案
    final answerPayload =
        (structured['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decision = AssistantTurnDecision.fromMaps(
      structured: structured,
      answerPayload: answerPayload,
    );
    if (decision.nextAction != AssistantNextAction.unknown &&
        decision.nextAction != AssistantNextAction.answer) {
      return '';
    }
    if (decision.messageKind == AssistantMessageKind.progress) return '';

    // Gate 2: uiAnswer.markdownText 是引擎层保证的纯文本，优先使用
    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdownText = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    if (markdownText.isNotEmpty &&
        !AssistantContentFilters.isNotDisplayable(markdownText)) {
      return markdownText;
    }

    // Gate 3: 从 finalText 用 LlmResponseParser 提取 userMarkdown
    final parsed = LlmResponseParser.parse(response.finalText);
    if (parsed.ok && !parsed.isIntermediateAction) {
      final um = parsed.userMarkdown;
      if (um.isNotEmpty && !AssistantContentFilters.isNotDisplayable(um)) {
        return um;
      }
    }
    return '';
  }

  List<String> _chunkText(String text) {
    final normalized = text.trim();
    if (normalized.isEmpty) return const <String>[];
    final pieces = <String>[];
    final buffer = StringBuffer();
    for (final rune in normalized.runes) {
      final ch = String.fromCharCode(rune);
      buffer.write(ch);
      final shouldSplit = ch == '\n' ||
          ch == '。' ||
          ch == '！' ||
          ch == '？' ||
          ch == '；' ||
          ch == ';' ||
          ch == '.' ||
          buffer.length >= 24;
      if (!shouldSplit) continue;
      pieces.add(buffer.toString());
      buffer.clear();
    }
    if (buffer.isNotEmpty) {
      pieces.add(buffer.toString());
    }
    return pieces;
  }

  Future<AssistantRunResponse?> _safeRemoteRun(
    AssistantRunRequest request,
  ) async {
    try {
      return await _openClawBridge.runRemote(request);
    } catch (_) {
      return null;
    }
  }

  Future<AssistantRunResponse?> _runRemoteWithStream(
    AssistantRunRequest request,
    StreamController<AssistantRunStreamEvent> controller,
  ) async {
    AssistantRunResponse? completed;
    var completedSeen = false;
    await for (final event in _openClawBridge.runRemoteStream(request)) {
      if (completedSeen) {
        // Strict ordering: ignore late events after completed.
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.trace &&
          event.trace != null) {
        controller.add(AssistantRunStreamEvent.trace(event.trace!));
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.chunk &&
          (event.chunkText?.isNotEmpty ?? false)) {
        controller.add(AssistantRunStreamEvent.chunk(event.chunkText!));
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.completed &&
          event.response != null) {
        completed = event.response;
        completedSeen = true;
      }
    }
    return completed;
  }

  void _emitSemanticEvent(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;

    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        controller.add(AssistantRunStreamEvent.planStarted(
          planSummary: event.message,
        ));
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: UserPhaseEventType.understandingStarted,
          message: '正在理解您的问题...',
        ));
        break;

      case AssistantTraceEventType.thinkingStarted:
        final hasEvidence = (event.data?['iteration'] as int? ?? 1) > 1;
        if (hasEvidence) {
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.analyzingStarted,
            message: '正在分析获取到的信息...',
          ));
        } else {
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.understandingStarted,
            message: '正在分析您的问题...',
          ));
        }
        controller.add(AssistantRunStreamEvent.thinkingProgress(event.message));
        break;

      case AssistantTraceEventType.thinkingProgress:
        final phase = (event.data?['phase'] as String?) ?? 'understanding';
        final phaseType = phase == 'analyzing'
            ? UserPhaseEventType.analyzingThinking
            : UserPhaseEventType.understandingThinking;
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: phaseType,
          message: event.message,
        ));
        controller.add(AssistantRunStreamEvent.thinkingProgress(event.message));
        break;

      case AssistantTraceEventType.toolStart:
        final toolName = (event.data?['stepId'] as String? ?? '')
            .split('_')
            .first;
        final actualToolName =
            (event.data?['tool'] ?? event.data?['toolName'] ?? toolName)
                .toString()
                .trim();
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: UserPhaseEventType.toolExecutionStarted,
          toolName: actualToolName,
          message: event.message,
          data: event.data,
        ));
        if (actualToolName.contains('search')) {
          controller.add(AssistantRunStreamEvent.searchProgress(
            '正在搜索: ${event.data?['query'] ?? event.message}',
          ));
        }
        break;

      case AssistantTraceEventType.toolResult:
        final isAssessment = event.data?['isAssessment'] == true;
        if (isAssessment) {
          final assessmentType =
              (event.data?['assessmentType'] as String?) ?? '';
          final userMsg =
              (event.data?['userMessage'] as String?) ?? event.message;
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.toolAssessmentResult,
            message: userMsg,
            data: <String, dynamic>{
              'assessmentType': assessmentType,
            },
          ));
        } else {
          final toolName = (event.data?['toolName'] ?? '').toString().trim();
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.toolExecutionCompleted,
            toolName: toolName,
            message: event.message,
            data: event.data,
          ));
          final refs = event.data?['references'] as List?;
          if (refs != null && refs.isNotEmpty) {
            controller.add(AssistantRunStreamEvent.searchProgress(
              '已获取 ${refs.length} 条结果',
            ));
          }
        }
        break;

      case AssistantTraceEventType.toolError:
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: UserPhaseEventType.toolAssessmentResult,
          message: '工具执行遇到问题',
          data: <String, dynamic>{'assessmentType': 'toolFailed'},
        ));
        break;

      case AssistantTraceEventType.replanTriggered:
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: UserPhaseEventType.toolAssessmentResult,
          message: event.message,
          data: <String, dynamic>{
            'assessmentType': event.data?['reason'] ?? 'needMoreSearch',
          },
        ));
        break;

      case AssistantTraceEventType.searchStarted:
      case AssistantTraceEventType.searchQueryGenerated:
        controller.add(AssistantRunStreamEvent.searchProgress(event.message));
        break;

      case AssistantTraceEventType.answerDelta:
        final delta = event.data?['delta'] as String? ?? event.message;
        controller.add(AssistantRunStreamEvent.answerDelta(delta));
        break;

      case AssistantTraceEventType.streamDelta:
        controller.add(AssistantRunStreamEvent.userPhase(
          phaseType: UserPhaseEventType.answeringDelta,
          message: event.message,
        ));
        controller.add(AssistantRunStreamEvent.answerDelta(event.message));
        break;

      case AssistantTraceEventType.lifecycleEnd:
        final data = event.data;
        if (data != null && data.containsKey('userMessage')) {
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.loopDegraded,
            message: data['userMessage'] as String? ?? '处理完成',
          ));
        }
        if (event.message.contains('finished')) {
          controller.add(AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.answeringCompleted,
            message: '回答完成',
          ));
        }
        break;

      default:
        break;
    }
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) async {
    if (mode == CapabilityRouteMode.localOnly) {
      return _assistantGateway.invokeSkill(
        skillId: skillId,
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
    }
    if (mode == CapabilityRouteMode.remotePreferred) {
      final remote = await _openClawBridge.invokeSkillRemote(
        skillId: skillId,
        arguments: arguments,
      );
      if (remote != null && remote['success'] == true) {
        return AssistantToolResult.fromJson(remote.cast<String, dynamic>());
      }
      return _assistantGateway.invokeSkill(
        skillId: skillId,
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
    }
    final local = await _assistantGateway.invokeSkill(
      skillId: skillId,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
    if (!local.success) {
      final remote = await _openClawBridge.invokeSkillRemote(
        skillId: skillId,
        arguments: arguments,
      );
      if (remote != null) {
        return AssistantToolResult.fromJson(remote.cast<String, dynamic>());
      }
    }
    return local;
  }
}
