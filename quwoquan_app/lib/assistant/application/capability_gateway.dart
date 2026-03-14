import 'dart:async';

import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/process_journal_bus.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';

enum CapabilityRouteMode { localOnly, remotePreferred, hybrid }

bool _alwaysEnabled() => true;

enum AssistantRunStreamEventType {
  trace,
  chunk,
  answerReset,
  completed,
  failed,
  planStarted,
  searchProgress,
  thinkingProgress,
  answerDelta,
  phaseTimeline,
  userPhaseEvent,
  userEvent,
  processUpdate,
  explainableFlowEvent,
  processJournalEvent,
}

enum ProcessStage { understanding, searching, analyzing, answering, completed }

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

enum ProcessContentBlockType { text, searchSummary, analysisSummary }

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
  final List<String> processLines;
  final List<ProcessContentBlock> contentBlocks;
  final bool isStreaming;
  final Map<String, dynamic> usageStats;
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
        'toolName': toolName,
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

  UserPhaseEventType? get userPhaseType {
    if (type != AssistantRunStreamEventType.userPhaseEvent) return null;
    final name = trace?.data?['userPhaseType'] as String?;
    if (name == null) return null;
    return UserPhaseEventType.values.firstWhere(
      (e) => e.name == name,
      orElse: () => UserPhaseEventType.understandingStarted,
    );
  }

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
    if (response.displayMarkdown.trim().isNotEmpty) return true;
    if (response.displayPlainText.trim().isNotEmpty) return true;
    if (response.structuredResponse.isNotEmpty) return true;
    return response.finalText.trim().isNotEmpty;
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
      if (!hasLiveAnswerDelta) {
        _resolveChunkDisplayText(response);
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

  bool _isUnsafeChunkDisplayCandidate(String raw) {
    final text = raw.trim();
    if (text.isEmpty) {
      return true;
    }
    if (AssistantContentFilters.isNotDisplayable(text)) {
      return true;
    }
    return text.contains('assistant_turn') ||
        text.contains('contractVersion') ||
        text.contains('queryTasks') ||
        text.contains('machineEnvelope') ||
        text.contains('<tool_call>') ||
        text.contains('</tool_call>') ||
        text.contains('tool_call');
  }

  String _resolveChunkDisplayText(AssistantRunResponse response) {
    final structured = response.structuredResponse;

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

    final artifactMarkdown = response.displayMarkdown;
    if (!_isUnsafeChunkDisplayCandidate(artifactMarkdown)) {
      return artifactMarkdown;
    }
    final artifactPlain = response.displayPlainText;
    if (!_isUnsafeChunkDisplayCandidate(artifactPlain)) {
      return artifactPlain;
    }

    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdownText = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    if (!_isUnsafeChunkDisplayCandidate(markdownText)) {
      return markdownText;
    }

    return '';
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
      if (event.type == OpenClawRemoteStreamEventType.processJournalEvent &&
          event.processJournalEvent != null) {
        controller.add(
          AssistantRunStreamEvent.processJournal(event.processJournalEvent!),
        );
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
