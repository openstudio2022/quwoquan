part of 'personal_assistant_stream_controller.dart';

const _assistantPresentationInvalidStreamFallback = 'invalid_stream_projection';

final class _AssistantRunStreamGeneration {
  _AssistantRunStreamGeneration({required this.sequence, required this.runId});

  final int sequence;
  String runId;
}

final class _PendingAssistantSteerCommand {
  const _PendingAssistantSteerCommand({
    required this.generationSequence,
    required this.runId,
    required this.instruction,
    required this.commandRequestId,
  });

  final int generationSequence;
  final String runId;
  final String instruction;
  final String commandRequestId;
}

extension PersonalAssistantRunStreamLifecycle
    on PersonalAssistantStreamController {
  _AssistantRunStreamGeneration _beginRunStreamGeneration({String runId = ''}) {
    final previousIterator = _activeRunStreamIterator;
    _runStreamGenerationSequence += 1;
    final generation = _AssistantRunStreamGeneration(
      sequence: _runStreamGenerationSequence,
      runId: runId.trim(),
    );
    _activeRunStreamGeneration = generation;
    _activeRunStreamIterator = null;
    _pendingSteerCommand = null;
    if (previousIterator != null) {
      unawaited(_cancelRunStreamIterator(previousIterator));
    }
    return generation;
  }

  bool _bindRunStreamGeneration(
    _AssistantRunStreamGeneration generation,
    String runId,
  ) {
    final normalizedRunId = runId.trim();
    if (normalizedRunId.isEmpty || !_isRunStreamGenerationCurrent(generation)) {
      return false;
    }
    generation.runId = normalizedRunId;
    return true;
  }

  bool _isRunStreamGenerationCurrent(
    _AssistantRunStreamGeneration generation, {
    String runId = '',
  }) {
    final active = _activeRunStreamGeneration;
    if (!_lifecycleRef.mounted ||
        active == null ||
        !identical(active, generation) ||
        active.sequence != generation.sequence) {
      return false;
    }
    final expectedRunId = runId.trim();
    return expectedRunId.isEmpty || active.runId == expectedRunId;
  }

  _AssistantRunStreamGeneration? _captureCurrentRunGeneration(String runId) {
    final normalizedRunId = runId.trim();
    final active = _activeRunStreamGeneration;
    if (normalizedRunId.isEmpty ||
        active == null ||
        active.runId != normalizedRunId ||
        _lifecycleState.runId.trim() != normalizedRunId ||
        !_isRunStreamGenerationCurrent(active, runId: normalizedRunId)) {
      return null;
    }
    return active;
  }

  bool _claimRunStreamIterator(
    _AssistantRunStreamGeneration generation,
    StreamIterator<AssistantStreamEventWire> iterator,
  ) {
    if (!_isRunStreamGenerationCurrent(generation)) {
      return false;
    }
    final previousIterator = _activeRunStreamIterator;
    _activeRunStreamIterator = iterator;
    if (previousIterator != null && !identical(previousIterator, iterator)) {
      unawaited(_cancelRunStreamIterator(previousIterator));
    }
    return true;
  }

  Future<bool> _consumeRunStream({
    required _AssistantRunStreamGeneration generation,
    required Stream<AssistantStreamEventWire> stream,
    required void Function(AssistantStreamEventWire event) onEvent,
    required bool Function() stopRequested,
  }) async {
    final iterator = StreamIterator<AssistantStreamEventWire>(stream);
    if (!_claimRunStreamIterator(generation, iterator)) {
      unawaited(_cancelRunStreamIterator(iterator));
      return false;
    }
    try {
      while (true) {
        final hasNext = await iterator.moveNext();
        if (!_isRunStreamGenerationCurrent(generation)) {
          return false;
        }
        if (!hasNext) {
          return true;
        }
        onEvent(iterator.current);
        if (!_isRunStreamGenerationCurrent(generation)) {
          return false;
        }
        if (stopRequested()) {
          return true;
        }
      }
    } finally {
      if (identical(_activeRunStreamIterator, iterator)) {
        _activeRunStreamIterator = null;
      }
      // Cancellation is initiated synchronously but must not keep the UI in a
      // running state while a transport waits for its own teardown receipt.
      unawaited(_cancelRunStreamIterator(iterator));
    }
  }

  Future<void> _cancelRunStreamIterator(
    StreamIterator<AssistantStreamEventWire> iterator,
  ) async {
    try {
      await iterator.cancel();
    } catch (error, stackTrace) {
      developer.log(
        'assistant stream cancellation failed',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  void _finishRunStreamGeneration(_AssistantRunStreamGeneration generation) {
    if (!_isRunStreamGenerationCurrent(generation)) {
      return;
    }
    final iterator = _activeRunStreamIterator;
    _activeRunStreamGeneration = null;
    _activeRunStreamIterator = null;
    _pendingSteerCommand = null;
    if (iterator != null) {
      unawaited(_cancelRunStreamIterator(iterator));
    }
  }

  void _disposeRunStreamLifecycle() {
    final iterator = _activeRunStreamIterator;
    _runStreamGenerationSequence += 1;
    _activeRunStreamGeneration = null;
    _activeRunStreamIterator = null;
    _pendingSteerCommand = null;
    if (iterator != null) {
      unawaited(_cancelRunStreamIterator(iterator));
    }
  }

  Future<void> openRunFromAppMessage(String runId) async {
    final trimmed = runId.trim();
    if (trimmed.isEmpty) {
      return;
    }
    final streamGeneration = _beginRunStreamGeneration(runId: trimmed);
    await ensureHistoryInitialized();
    if (!_isRunStreamGenerationCurrent(streamGeneration, runId: trimmed) ||
        !_lifecycleState.historyInitialized) {
      _finishRunStreamGeneration(streamGeneration);
      return;
    }
    _lifecycleState = _lifecycleState.copyWith(
      running: true,
      errorMessage: '',
      errorFailure: null,
      retryAvailable: false,
    );
    try {
      final run = await _lifecycleRef
          .read(assistantSessionRunFacetProvider)
          .getAssistantRun(runId: trimmed);
      if (!_isRunStreamGenerationCurrent(streamGeneration, runId: trimmed)) {
        return;
      }
      if (run.runId.trim() != trimmed || run.sessionId.trim().isEmpty) {
        throw const FormatException(
          'GetAssistantRun returned a mismatched run identity',
        );
      }
      final sameRun = _lifecycleState.runId.trim() == run.runId.trim();
      final terminal =
          _isAssistantTerminalRunStatus(run.status) ||
          run.streamState.completed;
      final targetEvents = _lifecycleState.events
          .where((event) => event.runId.trim() == run.runId.trim())
          .toList(growable: false);
      var transcript = List<AssistantTranscriptTimelineRow>.of(
        _lifecycleState.transcript,
      );
      var assistantRowId = '';
      AssistantAnswerTranscriptRow? existingAssistantRow;
      var openedProactiveTranscript = false;
      for (final row in transcript.reversed) {
        if (row is AssistantAnswerTranscriptRow &&
            row.anchor.runId.trim() == run.runId.trim()) {
          assistantRowId = row.id;
          existingAssistantRow = row;
          break;
        }
      }
      if (assistantRowId.isEmpty) {
        transcript = _appendOpenedRunTranscript(transcript, run);
        assistantRowId = 'proactive_${run.runId}';
        openedProactiveTranscript = true;
      }
      final terminalAnswer = run.terminalSnapshot?.answerText.trim() ?? '';
      final answer = terminal
          ? (terminalAnswer.isNotEmpty ? terminalAnswer : _openedRunAnswer(run))
          : (sameRun ? _lifecycleState.answer : '');
      final processSummary = sameRun
          ? _lifecycleState.processSummary
          : const PersonalAssistantProcessSummary();
      final presentationDocument = existingAssistantRow == null
          ? null
          : _presentationDocumentFromRowOrFallback(existingAssistantRow);
      transcript = openedProactiveTranscript
          ? transcript
                .map(
                  (row) => row.id == assistantRowId
                      ? _personalAssistantAssistantRow(
                          id: assistantRowId,
                          sessionId: run.sessionId,
                          text: answer,
                          runId: run.runId,
                          traceId: run.traceId,
                          sourceQuery: run.goal,
                          streaming: !terminal,
                          proactive: true,
                          processSummary: processSummary,
                        )
                      : row,
                )
                .toList(growable: false)
          : _upsertAssistantTranscript(
              transcript,
              assistantRowId,
              text: answer,
              runId: run.runId,
              traceId: run.traceId,
              sourceQuery: run.goal,
              streaming: !terminal,
              processSummary: processSummary,
              presentationDocument: presentationDocument,
            );
      if (!_isRunStreamGenerationCurrent(streamGeneration, runId: trimmed)) {
        return;
      }
      _lifecycleState = _lifecycleState.copyWith(
        sessionId: run.sessionId,
        runId: run.runId,
        runStatus: run.status,
        answer: answer,
        transcript: List<AssistantTranscriptTimelineRow>.unmodifiable(
          transcript,
        ),
        processSummary: processSummary,
        events: List<AssistantStreamEventWire>.unmodifiable(targetEvents),
        answerGateOpen: answer.isNotEmpty,
        running: !terminal,
        errorMessage: '',
        errorFailure: null,
        retryAvailable: false,
      );
      _clearRetry();
      if (terminal) {
        _finishRunStreamGeneration(streamGeneration);
        return;
      }
      await _watchContinuedRun(run.runId, generation: streamGeneration);
    } catch (error, stackTrace) {
      if (!_isRunStreamGenerationCurrent(streamGeneration, runId: trimmed)) {
        return;
      }
      developer.log(
        'open proactive run failed runId=$trimmed',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      _lifecycleState = _lifecycleState.copyWith(
        running: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: true,
      );
      _rememberRetry(_PersonalAssistantRetryKind.openRun, trimmed);
      _finishRunStreamGeneration(streamGeneration);
    }
  }

  Future<void> _ensureOpenPageContextReported() {
    final context = _openContext;
    if (context == null) {
      return Future<void>.value();
    }
    final inFlight = _pageContextReportFuture;
    if (inFlight != null) {
      return inFlight;
    }
    final report = () async {
      try {
        await _lifecycleRef
            .read(assistantPersonalizationFacetProvider)
            .reportPageContext(
              context: context,
              userAction: 'open_assistant_session',
            );
      } catch (_) {
        _pageContextReportFuture = null;
        rethrow;
      }
    }();
    _pageContextReportFuture = report;
    return report;
  }

  Future<void> _watchContinuedRun(
    String runId, {
    required _AssistantRunStreamGeneration generation,
  }) async {
    final normalizedRunId = runId.trim();
    if (!_isRunStreamGenerationCurrent(generation, runId: normalizedRunId)) {
      return;
    }
    final repository = _actionsRef.read(assistantSessionRunFacetProvider);
    AssistantAnswerTranscriptRow? assistantRow;
    for (final row
        in _actionsState.transcript.whereType<AssistantAnswerTranscriptRow>()) {
      if (row.anchor.runId.trim() == normalizedRunId) {
        assistantRow = row;
      }
    }
    if (assistantRow == null) {
      throw const FormatException(
        'Continued AssistantRun has no matching transcript row',
      );
    }
    final events = _actionsState.events
        .where((event) => event.runId.trim() == normalizedRunId)
        .toList(growable: true);
    var lastSeq = events.fold<int>(
      0,
      (maximum, event) => event.seq > maximum ? event.seq : maximum,
    );
    var answer = _actionsState.runId.trim() == normalizedRunId
        ? _actionsState.answer
        : assistantRow.content;
    var processSummary = _actionsState.processSummary;
    final presentationProjection = AssistantPresentationStreamProjection();
    AssistantPresentationDocumentWire? presentationDocument;
    presentationDocument = _presentationDocumentFromRowOrFallback(assistantRow);
    try {
      if (presentationDocument != null) {
        presentationProjection.seed(presentationDocument);
      }
    } on FormatException catch (error, stackTrace) {
      presentationDocument = null;
      developer.log(
        'assistant presentation resume snapshot degraded',
        name: 'assistant.presentation',
        error: error,
        stackTrace: stackTrace,
      );
      recordPresentationFallback(_assistantPresentationInvalidStreamFallback);
    }
    var transcript = <AssistantTranscriptTimelineRow>[
      ..._actionsState.transcript,
    ];
    var runStatus = _actionsState.runStatus;
    var terminalObserved = false;
    _actionsState = _actionsState.copyWith(running: true);
    final streamRemainedCurrent = await _consumeRunStream(
      generation: generation,
      stream: repository.watchAssistantRunEvents(
        runId: normalizedRunId,
        lastEventId: lastSeq > 0 ? lastSeq.toString() : '',
      ),
      onEvent: (event) {
        if (event.runId.trim() != normalizedRunId) {
          throw const FormatException(
            'AssistantRun stream returned a mismatched run identity',
          );
        }
        if (event.seq <= lastSeq) {
          return;
        }
        lastSeq = event.seq;
        events.add(event);
        final streamEvent = AssistantRunStreamEvent.fromWire(event);
        if (streamEvent.type ==
                AssistantRunStreamEventType.presentationSnapshot ||
            streamEvent.type ==
                AssistantRunStreamEventType.presentationCommit) {
          try {
            presentationDocument = presentationProjection.apply(event);
          } on FormatException catch (error, stackTrace) {
            developer.log(
              'assistant continued presentation stream degraded',
              name: 'assistant.presentation',
              error: error,
              stackTrace: stackTrace,
            );
            recordPresentationFallback(
              _assistantPresentationInvalidStreamFallback,
            );
          }
        }
        answer = _projectAnswer(answer, streamEvent);
        processSummary = _projectProcessSummary(
          processSummary,
          streamEvent,
          elapsedMs: processSummary.elapsedMs,
        );
        if (streamEvent.runStatus.isNotEmpty) {
          runStatus = streamEvent.runStatus;
        } else if (streamEvent.type == AssistantRunStreamEventType.completed) {
          runStatus = 'completed';
        } else if (streamEvent.type == AssistantRunStreamEventType.failed) {
          runStatus = 'failed';
        } else if (streamEvent.type == AssistantRunStreamEventType.cancelled) {
          runStatus = 'cancelled';
        }
        terminalObserved = terminalObserved || streamEvent.type.isTerminal;
        transcript = _upsertAssistantTranscript(
          transcript,
          assistantRow!.id,
          text: answer,
          runId: normalizedRunId,
          traceId: assistantRow.anchor.traceId,
          sourceQuery: assistantRow.anchor.sourceQuery,
          eventType: event.eventType.wireName,
          streaming: !streamEvent.type.isTerminal,
          processSummary: processSummary,
          presentationDocument: presentationDocument,
        );
        _actionsState = _actionsState.copyWith(
          running: !terminalObserved,
          runStatus: runStatus,
          answer: answer,
          transcript: transcript,
          processSummary: processSummary,
          events: List<AssistantStreamEventWire>.unmodifiable(events),
          answerGateOpen: _actionsState.answerGateOpen || answer.isNotEmpty,
        );
      },
      stopRequested: () => terminalObserved,
    );
    if (!streamRemainedCurrent ||
        !_isRunStreamGenerationCurrent(generation, runId: normalizedRunId)) {
      return;
    }
    if (!terminalObserved) {
      throw const FormatException(
        'Continued AssistantRun stream ended without a terminal event',
      );
    }
    _finishRunStreamGeneration(generation);
  }

  Future<void> _continueRunAfterAction(
    String runId,
    _AssistantRunStreamGeneration capturedGeneration,
  ) async {
    final normalizedRunId = runId.trim();
    if (!_isRunStreamGenerationCurrent(
      capturedGeneration,
      runId: normalizedRunId,
    )) {
      return;
    }
    final continuationGeneration = _beginRunStreamGeneration(
      runId: normalizedRunId,
    );
    try {
      await _watchContinuedRun(
        normalizedRunId,
        generation: continuationGeneration,
      );
    } catch (error, stackTrace) {
      if (!_isRunStreamGenerationCurrent(
        continuationGeneration,
        runId: normalizedRunId,
      )) {
        return;
      }
      developer.log(
        'assistant continued run failed runId=$normalizedRunId',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      _actionsState = _actionsState.copyWith(
        running: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: false,
      );
      _finishRunStreamGeneration(continuationGeneration);
    }
  }

  Future<bool> steerCurrentRun(String instruction) async {
    final normalized = instruction.trim();
    final runId = _actionsState.runId.trim();
    if (normalized.isEmpty ||
        runId.isEmpty ||
        !_actionsState.running ||
        _isAssistantTerminalRunStatus(_actionsState.runStatus)) {
      return false;
    }
    final capturedGeneration = _captureCurrentRunGeneration(runId);
    if (capturedGeneration == null) {
      return false;
    }
    final existing = _pendingSteerCommand;
    final command =
        existing != null &&
            existing.generationSequence == capturedGeneration.sequence &&
            existing.runId == runId &&
            existing.instruction == normalized
        ? existing
        : _PendingAssistantSteerCommand(
            generationSequence: capturedGeneration.sequence,
            runId: runId,
            instruction: normalized,
            commandRequestId: 'steer-${const Uuid().v4()}',
          );
    _pendingSteerCommand = command;
    try {
      final run = await _actionsRef
          .read(assistantRunControlFacetProvider)
          .steerAssistantRun(
            runId: runId,
            commandRequestId: command.commandRequestId,
            instruction: normalized,
          );
      if (!_isSteerCommandCurrent(capturedGeneration, command)) {
        return false;
      }
      if (run.runId.trim() != runId) {
        throw const FormatException(
          'SteerAssistantRun returned a mismatched run identity',
        );
      }
      _actionsState = _actionsState.copyWith(
        runStatus: run.status,
        running: !_isAssistantTerminalRunStatus(run.status),
        errorMessage: '',
        errorFailure: null,
        retryAvailable: false,
      );
      if (identical(_pendingSteerCommand, command)) {
        _pendingSteerCommand = null;
      }
      return true;
    } catch (error) {
      if (!_isSteerCommandCurrent(capturedGeneration, command)) {
        return false;
      }
      _actionsState = _actionsState.copyWith(
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: false,
      );
      return false;
    }
  }

  bool _isSteerCommandCurrent(
    _AssistantRunStreamGeneration generation,
    _PendingAssistantSteerCommand command,
  ) {
    return _isRunStreamGenerationCurrent(generation, runId: command.runId) &&
        identical(_pendingSteerCommand, command) &&
        _actionsState.runId.trim() == command.runId &&
        _actionsState.running &&
        !_isAssistantTerminalRunStatus(_actionsState.runStatus);
  }

  /// 结构解析已收敛到 Codec 边界（非法工件 fail-soft 置 null），
  /// 此处直读 typed 字段，不再有 FormatException 路径。
  AssistantPresentationDocumentWire? _presentationDocumentFromRow(
    AssistantAnswerTranscriptRow row,
  ) {
    return row.runArtifacts?.presentationDocument;
  }

  AssistantPresentationDocumentWire? _presentationDocumentFromRowOrFallback(
    AssistantAnswerTranscriptRow row,
  ) {
    return _presentationDocumentFromRow(row);
  }
}
