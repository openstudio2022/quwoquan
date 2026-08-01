part of 'assistant_repository.dart';

/// Assistant session, run lifecycle, and SSE transport.
mixin _RemoteAssistantSessionRun on _RemoteAssistantRepositoryBase
    implements AssistantSessionRunFacet, AssistantRunControlFacet {
  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AssistantApiMetadata.createAssistantSessionOperation,
    );
    final request = AssistantCreateSessionRequest(
      summary: summary.trim().isEmpty ? null : summary.trim(),
      clientRequestId: requestId,
    );
    final uri = _assistantUri(AssistantApiMetadata.createAssistantSessionPath);
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.createAssistantSessionOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.createAssistantSessionOperation,
          clientPageId: AssistantRequestPageIds.createAssistantSession,
        ),
        'Idempotency-Key': requestId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode(request.toJson()),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.createAssistantSessionOperation}',
    );
    final session = _assistantSessionWireFromProjection(
      decodeAssistantSession(
        _decodeAssistantObject(
          response,
          operationId: AssistantApiMetadata.createAssistantSessionOperation,
        ),
      ),
    );
    _debugAssistantRepository('session decoded id=${session.sessionId}');
    return session;
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) async {
    final session = await _sessionQuery.getSession(sessionId: sessionId);
    return _assistantSessionWireFromProjection(session);
  }

  @override
  Future<AssistantSessionListPage> listAssistantSessions({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final page = await _sessionQuery.listSessions(limit: limit, cursor: cursor);
    return AssistantSessionListPage(
      items: page.items
          .map(_assistantSessionWireFromProjection)
          .toList(growable: false),
      nextCursor: page.nextCursor ?? '',
    );
  }

  AssistantSessionWire _assistantSessionWireFromProjection(
    AssistantSessionProjection session,
  ) {
    return AssistantSessionWire(
      sessionId: session.sessionId,
      userId: session.userId,
      state: session.state,
      activeTurnId: session.activeTurnId,
      lastTurnId: session.lastTurnId,
      summary: session.summary,
      createdAt: session.createdAt.toUtc().toIso8601String(),
      updatedAt: session.updatedAt.toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final response = await _httpClient.get(
      _assistantGetUri(
        AssistantApiMetadata.listSessionTurnsPath(sessionId: sessionId),
        <String, String>{
          'limit': '$limit',
          if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
        },
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.listSessionTurnsOperation,
        clientPageId: AssistantRequestPageIds.listSessionTurns,
      ),
    );
    return AssistantTurnListView.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.listSessionTurnsOperation,
      ),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return _postAssistantRunCommand(
      path: AssistantApiMetadata.cancelAssistantRunPath(runId: runId),
      operationId: AssistantApiMetadata.cancelAssistantRunOperation,
      clientPageId: AssistantRequestPageIds.cancelAssistantRun,
      commandRequestId: commandRequestId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    return _postAssistantRunCommand(
      path: AssistantApiMetadata.pauseAssistantRunPath(runId: runId),
      operationId: AssistantApiMetadata.pauseAssistantRunOperation,
      clientPageId: AssistantRequestPageIds.pauseAssistantRun,
      commandRequestId: commandRequestId,
      body: <String, dynamic>{if (reason.trim().isNotEmpty) 'reason': reason},
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return _postAssistantRunCommand(
      path: AssistantApiMetadata.resumeAssistantRunPath(runId: runId),
      operationId: AssistantApiMetadata.resumeAssistantRunOperation,
      clientPageId: AssistantRequestPageIds.resumeAssistantRun,
      commandRequestId: commandRequestId,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    return _postAssistantRunCommand(
      path: AssistantApiMetadata.steerAssistantRunPath(runId: runId),
      operationId: AssistantApiMetadata.steerAssistantRunOperation,
      clientPageId: AssistantRequestPageIds.steerAssistantRun,
      commandRequestId: commandRequestId,
      body: <String, dynamic>{'instruction': instruction},
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> continueAssistantToolUse({
    required String runId,
    required String toolUseId,
    required String commandRequestId,
    required String decision,
    required String continuationToken,
    AssistantDeviceActionExecutionReceipt? executionReceipt,
  }) {
    return _postAssistantRunCommand(
      path: AssistantApiMetadata.continueAssistantToolUsePath(
        runId: runId,
        toolUseId: toolUseId,
      ),
      operationId: AssistantApiMetadata.continueAssistantToolUseOperation,
      clientPageId: AssistantRequestPageIds.continueAssistantToolUse,
      commandRequestId: commandRequestId,
      body: <String, dynamic>{
        'decision': decision,
        'continuationToken': continuationToken,
        'executionReceipt': executionReceipt?.toJson(),
      },
    );
  }

  Future<AssistantRunEnvelopeWire> _postAssistantRunCommand({
    required String path,
    required String operationId,
    required String clientPageId,
    required String commandRequestId,
    Map<String, dynamic>? body,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      commandRequestId,
      operation: operationId,
    );
    final response = await _httpClient.post(
      _assistantUri(path),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: operationId,
          clientPageId: clientPageId,
        ),
        'Idempotency-Key': requestId,
        if (body != null) 'Content-Type': 'application/json',
      },
      body: body == null ? null : jsonEncode(body),
    );
    return AssistantRunEnvelopeWire.fromJson(
      _decodeAssistantObject(response, operationId: operationId),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    final run = await _startAssistantRunIntent(
      sessionId: sessionId,
      clientRequestId: clientRequestId,
      intent: AssistantRunIntent(
        kind: AssistantRunIntentKind.answer,
        answer: AssistantAnswerRunIntent(text: text.trim()),
      ),
      contextSnapshot: intersectionEvidenceRefs.isEmpty
          ? null
          : AssistantContextSnapshot(
              intersectionEvidenceRefs:
                  List<AssistantIntersectionEvidenceRef>.unmodifiable(
                    intersectionEvidenceRefs,
                  ),
            ),
    );
    _debugAssistantRepository(
      'run decoded sessionId=${run.sessionId} runId=${run.runId} traceId=${run.traceId}',
    );
    return run;
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(AssistantApiMetadata.getAssistantRunPath(runId: runId)),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantRunOperation,
        clientPageId: AssistantRequestPageIds.getAssistantRun,
      ),
    );
    return AssistantRunEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantRunOperation,
      ),
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    final maxAttempts =
        _RemoteAssistantRepositoryBase._assistantStreamOperation.maxAttempts;
    if (maxAttempts < 1 ||
        _RemoteAssistantRepositoryBase._assistantStreamOperation.retryMode !=
            'idempotent') {
      throw StateError(
        'StreamAssistantRunEvents generated reliability contract is invalid',
      );
    }
    var lastSeq = int.tryParse(lastEventId) ?? 0;
    var resumeEventId = lastEventId.trim();
    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      var terminalEventObserved = false;
      try {
        await for (final frame in _openAssistantRunEventStream(
          runId: runId,
          lastEventId: resumeEventId,
        )) {
          final event = frame.event;
          if (event.seq <= lastSeq) {
            continue;
          }
          lastSeq = event.seq;
          if (frame.lastEventId.isNotEmpty) {
            resumeEventId = frame.lastEventId;
          }
          terminalEventObserved =
              terminalEventObserved || _isAssistantTerminalStreamEvent(event);
          yield event;
          if (terminalEventObserved) {
            return;
          }
        }
      } on CloudException catch (error) {
        if (!_isAssistantStreamRetryable(error) || attempt == maxAttempts) {
          rethrow;
        }
      } on FormatException {
        rethrow;
      } catch (error, stackTrace) {
        _debugAssistantRepository(
          'stream transport interrupted runId=$runId attempt=$attempt '
          'lastSeq=$lastSeq errorType=${error.runtimeType}',
        );
        if (attempt == maxAttempts) {
          Error.throwWithStackTrace(
            CloudErrorMapper.fromException(
              error,
              requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
                runId: runId,
              ),
            ),
            stackTrace,
          );
        }
      }
      if (terminalEventObserved) {
        return;
      }
      if (attempt == maxAttempts) {
        throw CloudErrorMapper.fromStatusCode(
          503,
          requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
            runId: runId,
          ),
        );
      }
      await Future<void>.delayed(
        _RemoteAssistantRepositoryBase._assistantStreamRetryPolicy.delayFor(
          attempt: attempt - 1,
        ),
      );
    }
  }

  Stream<_AssistantSseFrame> _openAssistantRunEventStream({
    required String runId,
    required String lastEventId,
  }) async* {
    final path = AssistantApiMetadata.streamAssistantRunEventsPath(
      runId: runId,
    );
    final uri = _assistantGetUri(path, <String, String>{
      if (lastEventId.isNotEmpty) 'resumeToken': lastEventId,
    });
    _debugAssistantRepository(
      'GET $uri operation=${AssistantApiMetadata.streamAssistantRunEventsOperation} runId=$runId',
    );
    final request = http.Request('GET', uri)
      ..headers.addAll(<String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.streamAssistantRunEventsOperation,
          clientPageId: AssistantRequestPageIds.streamAssistantRunEvents,
        ),
        if (lastEventId.isNotEmpty) 'Last-Event-ID': lastEventId,
      });
    final response = await _httpClient.send(request);
    _debugAssistantRepository(
      'stream response status=${response.statusCode} runId=$runId',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      // StreamedResponse 无同步 body；仅按状态码映射结构化异常。
      throw CloudErrorMapper.fromStatusCode(
        response.statusCode,
        requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
          runId: runId,
        ),
      );
    }
    final buffer = StringBuffer();
    await for (final piece in response.stream.transform(utf8.decoder)) {
      buffer.write(piece);
      var current = buffer.toString().replaceAll('\r\n', '\n');
      var splitIndex = current.indexOf('\n\n');
      while (splitIndex >= 0) {
        final frame = current.substring(0, splitIndex);
        final decoded = _decodeAssistantStreamFrame(frame);
        if (decoded != null) {
          _debugAssistantRepository(
            'sse event type=${decoded.event.eventType} '
            'seq=${decoded.event.seq} runId=$runId '
            'process=${AssistantRunStreamEvent.fromWire(decoded.event).process?.stage ?? ''}',
          );
          yield decoded;
        }
        current = current.substring(splitIndex + 2);
        splitIndex = current.indexOf('\n\n');
      }
      buffer
        ..clear()
        ..write(current);
    }
    final trailing = buffer.toString().trim();
    if (trailing.isNotEmpty) {
      final decoded = _decodeAssistantStreamFrame(trailing);
      if (decoded != null) {
        yield decoded;
      }
    }
  }
}
