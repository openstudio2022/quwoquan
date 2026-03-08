import 'dart:async';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
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
  // v5 formal user event stream
  userEvent,
  // v4 unified process update for single-drawer UI
  processUpdate,
}

/// Unified process state consumed by the single-drawer process view.
/// Aggregated from individual trace/phase events.
enum ProcessStage { understanding, searching, analyzing, answering, completed }

/// A single reference document discovered during search or analysis.
class ProcessReference {
  const ProcessReference({
    required this.title,
    required this.url,
    this.source = '',
  });

  final String title;
  final String url;
  final String source;
}

/// Block types rendered inside the process drawer body.
enum ProcessContentBlockType { text, searchSummary, analysisSummary }

/// A structured content block within the process drawer.
///
/// - [text]: plain thinking/reasoning line.
/// - [searchSummary]: "搜索了 X 篇文档" with a collapsible reference list.
/// - [analysisSummary]: "分析参考了 X 篇文档" with a collapsible reference list.
class ProcessContentBlock {
  const ProcessContentBlock({
    required this.type,
    this.text = '',
    this.references = const <ProcessReference>[],
  });

  final ProcessContentBlockType type;
  final String text;
  final List<ProcessReference> references;
}

class AssistantProcessState {
  const AssistantProcessState({
    this.stage = ProcessStage.understanding,
    this.stageLabel = '正在理解问题',
    this.processLines = const <String>[],
    this.contentBlocks = const <ProcessContentBlock>[],
    this.isStreaming = false,
    this.usageStats = const <String, dynamic>{},
    this.elapsedMs = 0,
  });

  final ProcessStage stage;
  final String stageLabel;

  /// Legacy flat lines — used when [contentBlocks] is empty.
  final List<String> processLines;

  /// Structured content blocks with nested reference lists.
  final List<ProcessContentBlock> contentBlocks;
  final bool isStreaming;

  /// Model usage stats: modelCallCount, totalTokens, maxTokensPerCall.
  final Map<String, dynamic> usageStats;

  /// Total elapsed time in milliseconds for the entire run.
  final int elapsedMs;

  AssistantProcessState copyWith({
    ProcessStage? stage,
    String? stageLabel,
    List<String>? processLines,
    List<ProcessContentBlock>? contentBlocks,
    bool? isStreaming,
    Map<String, dynamic>? usageStats,
    int? elapsedMs,
  }) {
    return AssistantProcessState(
      stage: stage ?? this.stage,
      stageLabel: stageLabel ?? this.stageLabel,
      processLines: processLines ?? this.processLines,
      contentBlocks: contentBlocks ?? this.contentBlocks,
      isStreaming: isStreaming ?? this.isStreaming,
      usageStats: usageStats ?? this.usageStats,
      elapsedMs: elapsedMs ?? this.elapsedMs,
    );
  }

  AssistantProcessState appendLine(String line) {
    return copyWith(processLines: [...processLines, line]);
  }

  AssistantProcessState appendBlock(ProcessContentBlock block) {
    return copyWith(contentBlocks: [...contentBlocks, block]);
  }
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
  ) => AssistantRunStreamEvent._(
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
  }) => AssistantRunStreamEvent._(
    type: AssistantRunStreamEventType.userPhaseEvent,
    trace: AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: message ?? phaseType.name,
      timestamp: DateTime.now(),
      data: <String, dynamic>{
        'userPhaseType': phaseType.name,
        'toolName': ?toolName,
        ...?data,
      },
    ),
    chunkText: message,
  );

  factory AssistantRunStreamEvent.processUpdate(AssistantProcessState state) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.processUpdate,
        chunkText: state.stageLabel,
        trace: AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleStart,
          message: state.stageLabel,
          timestamp: DateTime.now(),
          data: <String, dynamic>{
            'stage': state.stage.name,
            'processLines': state.processLines,
            'isStreaming': state.isStreaming,
          },
        ),
      );

  factory AssistantRunStreamEvent.userEvent(UserEvent event) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.userEvent,
        chunkText: event.message,
        trace: AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleStart,
          message: event.message,
          timestamp: DateTime.now(),
          data: event.toJson(),
        ),
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

  UserEvent? get userFacingEvent {
    if (type != AssistantRunStreamEventType.userEvent) return null;
    final data = trace?.data;
    if (data == null) return null;
    return UserEvent.fromJson(data);
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
        controller.add(
          AssistantRunStreamEvent.completed(
            _buildGatewayErrorResponse(request, error, 'runstream_outer'),
          ),
        );
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
          _emitUserEvent(event, controller);
        },
      );
      final userEvents = (response.structuredResponse['userEvents'] as List?)
          ?.whereType<Map>()
          .map((item) => UserEvent.fromJson(item.cast<String, dynamic>()))
          .toList(growable: false);
      if (userEvents != null && userEvents.isNotEmpty && !controller.isClosed) {
        for (final event in userEvents) {
          controller.add(AssistantRunStreamEvent.userEvent(event));
        }
      }
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

  /// 静默运行本地网关：只发 trace 事件和语义阶段事件，不发 chunk。
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
            // 静默路径同样需要语义化，确保 UI 过程抽屉阶段正确推进
            _emitSemanticEvent(event, controller);
            _emitUserEvent(event, controller);
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
    if (parsed.ok) {
      final um = parsed.userMarkdown;
      if (um.isNotEmpty && !AssistantContentFilters.isNotDisplayable(um)) {
        return um;
      }
    }

    // Gate 4: answerPayload.userMarkdown
    final userMd = (answerPayload['userMarkdown'] as String?)?.trim() ?? '';
    if (userMd.isNotEmpty &&
        !AssistantContentFilters.isNotDisplayable(userMd)) {
      return userMd;
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
      final shouldSplit =
          ch == '\n' ||
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
        // 远端 trace 事件同样需要语义化，确保 UI 过程抽屉阶段正确推进
        _emitSemanticEvent(event.trace!, controller);
        _emitUserEvent(event.trace!, controller);
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.userEvent &&
          event.userEvent != null) {
        controller.add(AssistantRunStreamEvent.userEvent(event.userEvent!));
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

  void _emitUserEvent(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    final userEvent = _UserEventTranslator.translate(event);
    if (userEvent == null || controller.isClosed) return;
    controller.add(AssistantRunStreamEvent.userEvent(userEvent));
  }

  void _emitSemanticEvent(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;

    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        controller.add(
          AssistantRunStreamEvent.planStarted(planSummary: event.message),
        );
        controller.add(
          AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.understandingStarted,
            message: '正在理解您的问题...',
          ),
        );
        break;

      case AssistantTraceEventType.thinkingStarted:
        final hasEvidence = (event.data?['iteration'] as int? ?? 1) > 1;
        if (hasEvidence) {
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.analyzingStarted,
              message: '正在分析获取到的信息...',
            ),
          );
        } else {
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.understandingStarted,
              message: '正在分析您的问题...',
            ),
          );
        }
        controller.add(AssistantRunStreamEvent.thinkingProgress(event.message));
        break;

      case AssistantTraceEventType.thinkingProgress:
        final phase = (event.data?['phase'] as String?) ?? 'understanding';
        final isExtracted = event.data?['extracted'] == true;
        final phaseType = phase == 'analyzing'
            ? UserPhaseEventType.analyzingThinking
            : phase == 'answering'
            ? UserPhaseEventType.answeringStarted
            : UserPhaseEventType.understandingThinking;
        controller.add(
          AssistantRunStreamEvent.userPhase(
            phaseType: phaseType,
            message: event.message,
            data: isExtracted ? <String, dynamic>{'extracted': true} : null,
          ),
        );
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
        controller.add(
          AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.toolExecutionStarted,
            toolName: actualToolName,
            message: event.message,
            data: event.data,
          ),
        );
        if (actualToolName.contains('search')) {
          controller.add(
            AssistantRunStreamEvent.searchProgress(
              '正在搜索: ${event.data?['query'] ?? event.message}',
            ),
          );
        }
        break;

      case AssistantTraceEventType.toolResult:
        final isAssessment = event.data?['isAssessment'] == true;
        if (isAssessment) {
          final assessmentType =
              (event.data?['assessmentType'] as String?) ?? '';
          final userMsg =
              (event.data?['userMessage'] as String?) ?? event.message;
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.toolAssessmentResult,
              message: userMsg,
              data: <String, dynamic>{'assessmentType': assessmentType},
            ),
          );
        } else {
          final toolName = (event.data?['toolName'] ?? '').toString().trim();
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.toolExecutionCompleted,
              toolName: toolName,
              message: event.message,
              data: event.data,
            ),
          );
          final refs = event.data?['references'] as List?;
          if (refs != null && refs.isNotEmpty) {
            controller.add(
              AssistantRunStreamEvent.searchProgress('已获取 ${refs.length} 条结果'),
            );
          }
        }
        break;

      case AssistantTraceEventType.toolError:
        controller.add(
          AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.toolAssessmentResult,
            message: '工具执行遇到问题',
            data: <String, dynamic>{'assessmentType': 'toolFailed'},
          ),
        );
        break;

      case AssistantTraceEventType.replanTriggered:
        controller.add(
          AssistantRunStreamEvent.userPhase(
            phaseType: UserPhaseEventType.toolAssessmentResult,
            message: event.message,
            data: <String, dynamic>{
              'assessmentType': event.data?['reason'] ?? 'needMoreSearch',
            },
          ),
        );
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
        break;

      case AssistantTraceEventType.lifecycleEnd:
        final data = event.data;
        if (data != null && data.containsKey('userMessage')) {
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.loopDegraded,
              message: data['userMessage'] as String? ?? '处理完成',
            ),
          );
        }
        if (event.message.contains('finished')) {
          controller.add(
            AssistantRunStreamEvent.userPhase(
              phaseType: UserPhaseEventType.answeringCompleted,
              message: '回答完成',
            ),
          );
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

class _UserEventTranslator {
  static UserEvent? translate(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    switch (event.type) {
      case AssistantTraceEventType.planStarted:
        return const UserEvent(
          type: UserEventType.processReplace,
          scope: UserEventScope.root,
          nodeId: 'root.intent',
          message: '已理解你的问题，准备开始处理',
        );
      case AssistantTraceEventType.toolStart:
        if (_isSearchLike(event, data)) {
          final toolName = _toolName(data);
          return UserEvent(
            type: UserEventType.processAppend,
            scope: UserEventScope.skill,
            nodeId: toolName.isEmpty ? 'skill.search' : 'skill.$toolName',
            message: '正在补充与问题相关的信息',
            payload: <String, dynamic>{'toolName': toolName},
          );
        }
        return null;
      case AssistantTraceEventType.toolResult:
        if (data['isAssessment'] == true) {
          final userMessage = _sanitizeMessage(
            (data['userMessage'] as String?)?.trim() ?? '',
          );
          if (userMessage.isEmpty) return null;
          return UserEvent(
            type: UserEventType.processAppend,
            scope: UserEventScope.aggregation,
            nodeId: 'aggregation.assessment',
            message: userMessage,
          );
        }
        final refs = (data['references'] as List?)?.length ?? 0;
        if (refs > 0) {
          return UserEvent(
            type: UserEventType.processAppend,
            scope: UserEventScope.skill,
            nodeId: _toolName(data),
            message: '已核对 $refs 个来源，继续整理关键信息',
            payload: <String, dynamic>{'referenceCount': refs},
          );
        }
        return null;
      case AssistantTraceEventType.subagentStart:
        final goal = _sanitizeMessage((data['goal'] as String?)?.trim() ?? '');
        return UserEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: (data['domainId'] as String?)?.trim() ?? 'skill.secondary',
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          message: goal.isNotEmpty ? goal : '正在并行补充另一部分信息',
          payload: data,
        );
      case AssistantTraceEventType.subagentResult:
        return UserEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.skill,
          nodeId: (data['domainId'] as String?)?.trim() ?? 'skill.secondary',
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          message: _summarizeSubtask(data),
          payload: data,
        );
      case AssistantTraceEventType.subagentError:
        return UserEvent(
          type: UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: (data['domainId'] as String?)?.trim() ?? 'skill.secondary',
          runId: (data['subagentId'] as String?)?.trim() ?? '',
          message: '这部分信息暂时还不完整，我继续用已有信息整理结果',
          payload: data,
        );
      case AssistantTraceEventType.lifecycleEnd:
        final userMessage = _sanitizeMessage(
          (data['userMessage'] as String?)?.trim() ?? '',
        );
        if (userMessage.isEmpty) return null;
        return UserEvent(
          type: UserEventType.processCommit,
          scope: UserEventScope.aggregation,
          nodeId: 'aggregation.final',
          message: userMessage,
          payload: data,
        );
      default:
        return null;
    }
  }

  static bool _isSearchLike(
    AssistantTraceEvent event,
    Map<String, dynamic> data,
  ) {
    final toolName = _toolName(data).toLowerCase();
    if (toolName.contains('search') || toolName.contains('fetch')) {
      return true;
    }
    return event.message.toLowerCase().contains('search');
  }

  static String _toolName(Map<String, dynamic> data) {
    return (data['toolName'] ?? data['tool'] ?? data['stepId'] ?? '')
        .toString()
        .split('_')
        .first
        .trim();
  }

  static String _summarizeSubtask(Map<String, dynamic> data) {
    final summary = _sanitizeMessage((data['summary'] as String?)?.trim() ?? '');
    if (summary.isNotEmpty) return summary;
    final goal = _sanitizeMessage((data['goal'] as String?)?.trim() ?? '');
    if (goal.isNotEmpty) return '已完成：$goal';
    return '已完成这部分信息整理';
  }

  static String _sanitizeMessage(String raw) {
    var text = raw.trim();
    if (text.isEmpty) return '';
    const blockedFragments = <String>[
      'queryVariants',
      'freshnessHoursMax',
      'provider',
      'contractVersion',
      'assistant_turn_v4',
      'tool_call',
      '<tool_call>',
      '</tool_call>',
      'timeScope',
    ];
    for (final fragment in blockedFragments) {
      if (text.contains(fragment)) return '';
    }
    if (text.startsWith('{') || text.startsWith('[')) return '';
    return text;
  }
}
