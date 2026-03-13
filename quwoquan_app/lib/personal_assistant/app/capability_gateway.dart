import 'dart:async';

import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_response_parser.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_journal_bus.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

enum CapabilityRouteMode { localOnly, remotePreferred, hybrid }

bool _alwaysEnabled() => true;

enum AssistantRunStreamEventType {
  trace,
  chunk,
  answerReset,
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
  // v6 unified explainable flow event (replaces v2-v5 for process drawer)
  explainableFlowEvent,
  // v7 canonical user-facing process bus
  processJournalEvent,
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
    this.explainableEvent,
    this.processJournalEvent,
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

  factory AssistantRunStreamEvent.answerReset() =>
      const AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.answerReset,
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

  factory AssistantRunStreamEvent.explainableFlow(ExplainableFlowEvent event) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.explainableFlowEvent,
        chunkText: event.headline,
        explainableEvent: event,
      );

  factory AssistantRunStreamEvent.processJournal(ProcessJournalEvent event) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.processJournalEvent,
        chunkText: event.message,
        processJournalEvent: event,
      );

  final AssistantRunStreamEventType type;
  final AssistantTraceEvent? trace;
  final String? chunkText;
  final AssistantRunResponse? response;
  final String? errorMessage;
  final ExplainableFlowEvent? explainableEvent;
  final ProcessJournalEvent? processJournalEvent;

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
    bool Function()? isPersonalContentAccessGranted,
    bool Function()? isAssistantContentIdentityIndexEnabled,
  }) : _assistantGateway = assistantGateway,
       _openClawBridge = openClawBridge,
       _isPersonalContentAccessGranted =
           isPersonalContentAccessGranted ?? _alwaysEnabled,
       _isAssistantContentIdentityIndexEnabled =
           isAssistantContentIdentityIndexEnabled ?? _alwaysEnabled {
    _openClawBridge.bindLocalGateway(assistantGateway);
  }

  final AssistantGateway _assistantGateway;
  final OpenClawBridge _openClawBridge;
  final bool Function() _isPersonalContentAccessGranted;
  final bool Function() _isAssistantContentIdentityIndexEnabled;

  ProcessJournalBus? _journalBus;

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
    final effectiveRequest = _applyPersonalContentAccessPolicy(request);
    await AssistantContentFilters.ensureLoaded();
    if (mode == CapabilityRouteMode.localOnly) {
      return _safeLocalRun(effectiveRequest);
    }
    if (mode == CapabilityRouteMode.remotePreferred) {
      final remote = await _safeRemoteRun(effectiveRequest);
      if (remote != null && _isRemoteResponseCommercialReady(remote)) {
        return remote;
      }
      return _safeLocalRun(effectiveRequest);
    }
    final local = await _safeLocalRun(effectiveRequest);
    if (local.degraded) {
      final remote = await _safeRemoteRun(effectiveRequest);
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
        final effectiveRequest = _applyPersonalContentAccessPolicy(request);
        await AssistantContentFilters.ensureLoaded();
        if (mode == CapabilityRouteMode.localOnly) {
          final local = await _runLocalWithStream(effectiveRequest, controller);
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        if (mode == CapabilityRouteMode.remotePreferred) {
          final remote = await _runRemoteWithStream(
            effectiveRequest,
            controller,
          );
          if (remote != null && _isRemoteResponseCommercialReady(remote)) {
            controller.add(AssistantRunStreamEvent.completed(remote));
            return;
          }
          // Remote 不满足要求时，显式重置答案流，再走 local，
          // 避免 keep-alive 空 chunk 和“清空正文”共用同一语义。
          controller.add(AssistantRunStreamEvent.answerReset());
          final local = await _runLocalWithStreamSilent(
            effectiveRequest,
            controller,
          );
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final local = await _runLocalWithStream(effectiveRequest, controller);
        if (!local.degraded) {
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final remote = await _safeRemoteRun(effectiveRequest);
        if (remote != null && _isRemoteResponseCommercialReady(remote)) {
          _journalBus = ProcessJournalBus(
            userGoalSummary: _extractUserMessage(effectiveRequest),
          );
          for (final trace in remote.traces) {
            _emitCanonicalTraceEvent(trace, controller);
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

  AssistantRunRequest _applyPersonalContentAccessPolicy(
    AssistantRunRequest request,
  ) {
    final consentGranted = _isPersonalContentAccessGranted();
    final identityIndexEnabled = _isAssistantContentIdentityIndexEnabled();
    final basePrivacyPolicy = <String, dynamic>{
      ...((request.contextScopeHint['privacyPolicy'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{}),
      ...request.privacyPolicy,
    };
    final allowedProviders = _stringList(basePrivacyPolicy['allowedProviders']);
    final blockedProviders = _stringList(basePrivacyPolicy['blockedProviders']);
    if (!consentGranted) {
      allowedProviders.remove('page_context');
      if (!blockedProviders.contains('page_context')) {
        blockedProviders.add('page_context');
      }
    }
    final nextPrivacyPolicy = <String, dynamic>{
      ...basePrivacyPolicy,
      if (allowedProviders.isNotEmpty) 'allowedProviders': allowedProviders,
      'blockedProviders': blockedProviders,
    };
    final nextContextScope = <String, dynamic>{
      ...request.contextScopeHint,
      'assistantContentAccess': <String, dynamic>{
        'skillId': kPersonalContentAccessSkillId,
        'granted': consentGranted,
        'grantedScope': kPersonalContentAccessSkillId,
      },
      'assistantContentIndex': <String, dynamic>{
        'enabled': identityIndexEnabled,
        'fallbackReason': consentGranted
            ? (identityIndexEnabled ? '' : 'feature_flag_disabled')
            : 'consent_denied',
      },
      'privacyPolicy': nextPrivacyPolicy,
    };
    if (!consentGranted) {
      nextContextScope.remove('behaviorTimeline');
    }
    return AssistantRunRequest(
      messages: request.messages,
      sessionId: request.sessionId,
      userId: request.userId,
      deviceProfile: request.deviceProfile,
      deviceModel: request.deviceModel,
      deviceOs: request.deviceOs,
      gpsLocation: request.gpsLocation,
      channel: request.channel,
      traceId: request.traceId,
      maxIterations: request.maxIterations,
      capabilityCatalog: request.capabilityCatalog,
      contextScopeHint: nextContextScope,
      privacyProfile: request.privacyProfile,
      privacyPolicy: nextPrivacyPolicy,
      userProfileSnapshot: request.userProfileSnapshot,
      rewriteInstruction: request.rewriteInstruction,
    );
  }

  List<String> _stringList(Object? raw) {
    if (raw is! List) return <String>[];
    return raw
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: true);
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
      _journalBus = ProcessJournalBus(
        userGoalSummary: _extractUserMessage(request),
      );
      var hasLiveAnswerDelta = false;
      final response = await _assistantGateway.runWithTraceStream(
        request,
        onTraceEvent: (event) {
          if (controller.isClosed) return;
          final delta = _traceAnswerDelta(event);
          if (delta.isNotEmpty) {
            hasLiveAnswerDelta = true;
          }
          _emitCanonicalTraceEvent(event, controller);
        },
      );
      final chunkText = _resolveChunkDisplayText(response);
      if (chunkText.isNotEmpty && !controller.isClosed && !hasLiveAnswerDelta) {
        for (final chunk in _chunkText(chunkText)) {
          if (chunk.trim().isEmpty) continue;
          controller.add(AssistantRunStreamEvent.answerDelta(chunk));
          controller.add(
            AssistantRunStreamEvent.processJournal(
              ProcessJournalEvent(
                eventId:
                    'answer_delta_fallback_${DateTime.now().microsecondsSinceEpoch}',
                type: ProcessJournalEventType.answerDelta,
                stage: 'answering',
                nodeId: 'answer.stream',
                message: chunk,
              ),
            ),
          );
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
        _emitCanonicalTraceEvent(trace, controller);
      }
      return fallback;
    }
  }

  /// 静默运行本地网关：只发用户态过程事件，不补发答案 chunk。
  /// 用于 remote 失败 fallback 到 local 的场景，避免两路答案增量叠加。
  Future<AssistantRunResponse> _runLocalWithStreamSilent(
    AssistantRunRequest request,
    StreamController<AssistantRunStreamEvent> controller,
  ) async {
    try {
      _journalBus = ProcessJournalBus(
        userGoalSummary: _extractUserMessage(request),
      );
      final response = await _assistantGateway.runWithTraceStream(
        request,
        onTraceEvent: (event) {
          _emitCanonicalTraceEvent(event, controller);
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
        _emitCanonicalTraceEvent(trace, controller);
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
          visibility: TraceVisibility.system,
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

    // Gate 2: completed artifact 的展示账是最终真相源
    final artifactMarkdown = response.displayMarkdownV1;
    if (artifactMarkdown.isNotEmpty &&
        !AssistantContentFilters.isNotDisplayable(artifactMarkdown)) {
      return artifactMarkdown;
    }
    final artifactPlain = response.displayPlainTextV1;
    if (artifactPlain.isNotEmpty &&
        !AssistantContentFilters.isNotDisplayable(artifactPlain)) {
      return artifactPlain;
    }

    // Gate 3: uiAnswer.markdownText 是引擎层保证的纯文本，优先使用
    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdownText = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    if (markdownText.isNotEmpty &&
        !AssistantContentFilters.isNotDisplayable(markdownText)) {
      return markdownText;
    }

    // Gate 4: 从 finalText 用 LlmResponseParser 提取 userMarkdown
    final parsed = LlmResponseParser.parse(response.finalText);
    if (parsed.ok) {
      final um = parsed.userMarkdown;
      if (um.isNotEmpty && !AssistantContentFilters.isNotDisplayable(um)) {
        return um;
      }
    }

    // Gate 5: answerPayload.userMarkdown
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
    _journalBus = ProcessJournalBus(
      userGoalSummary: _extractUserMessage(request),
    );
    AssistantRunResponse? completed;
    var completedSeen = false;
    await for (final event in _openClawBridge.runRemoteStream(request)) {
      if (completedSeen) {
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.failed) {
        return null;
      }
      if (event.type == OpenClawRemoteStreamEventType.trace &&
          event.trace != null) {
        _emitCanonicalTraceEvent(event.trace!, controller);
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.userEvent &&
          event.userEvent != null) {
        _emitCanonicalUserEvent(event.userEvent!, controller);
        continue;
      }
      if (event.type == OpenClawRemoteStreamEventType.chunk &&
          (event.chunkText?.isNotEmpty ?? false)) {
        controller.add(AssistantRunStreamEvent.answerDelta(event.chunkText!));
        controller.add(
          AssistantRunStreamEvent.processJournal(
            ProcessJournalEvent(
              eventId:
                  'answer_delta_remote_${DateTime.now().microsecondsSinceEpoch}',
              type: ProcessJournalEventType.answerDelta,
              stage: 'answering',
              nodeId: 'answer.stream',
              message: event.chunkText!,
            ),
          ),
        );
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

  static String _extractUserMessage(AssistantRunRequest request) {
    for (int i = request.messages.length - 1; i >= 0; i--) {
      final m = request.messages[i];
      if (m.role == 'user' && m.content.trim().isNotEmpty) {
        return m.content.trim();
      }
    }
    return '';
  }

  void _emitProcessJournalEvent(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    final journalBus = _journalBus;
    if (journalBus == null || controller.isClosed) return;
    final events = journalBus.consumeTrace(event);
    for (final item in events) {
      if (controller.isClosed) return;
      controller.add(AssistantRunStreamEvent.processJournal(item));
    }
  }

  void _emitCanonicalTraceEvent(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;
    final delta = _traceAnswerDelta(event);
    if (delta.isNotEmpty) {
      controller.add(AssistantRunStreamEvent.answerDelta(delta));
    }
    _emitProcessJournalEvent(event, controller);
  }

  void _emitCanonicalUserEvent(
    UserEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;
    if (event.type == UserEventType.answerDelta &&
        event.message.trim().isNotEmpty) {
      controller.add(AssistantRunStreamEvent.answerDelta(event.message));
    }
    final journalEvents = _journalBus?.consumeUserEvent(event);
    if (journalEvents == null) return;
    for (final item in journalEvents) {
      if (controller.isClosed) return;
      controller.add(AssistantRunStreamEvent.processJournal(item));
    }
  }

  String _traceAnswerDelta(AssistantTraceEvent event) {
    if (event.type != AssistantTraceEventType.answerDelta &&
        event.type != AssistantTraceEventType.streamDelta) {
      return '';
    }
    return ((event.data?['delta'] as String?) ?? event.message).trim();
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
