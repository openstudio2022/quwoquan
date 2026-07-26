part of 'assistant_repository.dart';

/// Assistant conversation, run lifecycle, and SSE transport.
mixin _RemoteAssistantConversationRun on _RemoteAssistantRepositoryBase
    implements AssistantConversationRunFacet {
  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
    required String clientRequestId,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AssistantApiMetadata.createAssistantConversationOperation,
    );
    final request = AssistantCreateConversationRequest(
      summary: summary.trim().isEmpty ? null : summary.trim(),
      clientRequestId: requestId,
    );
    final uri = _assistantUri(
      AssistantApiMetadata.createAssistantConversationPath,
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.createAssistantConversationOperation,
          clientPageId: AssistantRequestPageIds.createAssistantConversation,
        ),
        'Idempotency-Key': requestId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode(request.toJson()),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final conversation = AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createAssistantConversationOperation,
      ),
    );
    _debugAssistantRepository(
      'conversation decoded id=${conversation.conversationId}',
    );
    return conversation;
  }

  @override
  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(
        AssistantApiMetadata.getAssistantConversationPath(
          conversationId: conversationId,
        ),
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
        clientPageId: AssistantRequestPageIds.getAssistantConversation,
      ),
    );
    return AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
      ),
    );
  }

  @override
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final response = await _httpClient.get(
      _assistantGetUri(
        AssistantApiMetadata.listAssistantConversationsPath,
        <String, String>{
          'limit': '$limit',
          if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
        },
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.listAssistantConversationsOperation,
        clientPageId: AssistantRequestPageIds.listAssistantConversations,
      ),
    );
    return AssistantConversationListPage.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.listAssistantConversationsOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final response = await _httpClient.get(
      _assistantGetUri(
        AssistantApiMetadata.listConversationTurnsPath(
          conversationId: conversationId,
        ),
        <String, String>{
          'limit': '$limit',
          if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
        },
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.listConversationTurnsOperation,
        clientPageId: AssistantRequestPageIds.listConversationTurns,
      ),
    );
    return AssistantTurnListView.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.listConversationTurnsOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({
    required String runId,
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.cancelAssistantRunPath(runId: runId),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.cancelAssistantRunOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.cancelAssistantRunOperation,
        clientPageId: AssistantRequestPageIds.cancelAssistantRun,
      ),
    );
    return AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.cancelAssistantRunOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AssistantApiMetadata.startAssistantRunOperation,
    );
    final request = AssistantStartRunRequest(
      turnType: turnType.trim().isEmpty ? null : turnType.trim(),
      skillId: skillId.trim().isEmpty ? null : skillId.trim(),
      domainId: domainId.trim().isEmpty ? null : domainId.trim(),
      input: AssistantRunTextInput(text: text.trim()),
      trigger: const AssistantRunTrigger(type: 'user_message'),
      clientRequestId: requestId,
      contextSnapshot: intersectionEvidenceRefs.isEmpty
          ? null
          : AssistantContextSnapshot(
              intersectionEvidenceRefs:
                  List<AssistantIntersectionEvidenceRef>.unmodifiable(
                    intersectionEvidenceRefs,
                  ),
            ),
    );
    final uri = _assistantUri(
      AssistantApiMetadata.startAssistantRunPath(
        conversationId: conversationId,
      ),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.startAssistantRunOperation} '
      'conversationId=$conversationId text="${_assistantDebugSnippet(text)}"',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.startAssistantRunOperation,
          clientPageId: AssistantRequestPageIds.startAssistantRun,
        ),
        'Idempotency-Key': requestId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode(request.toJson()),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.startAssistantRunOperation}',
    );
    final turn = AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.startAssistantRunOperation,
      ),
    );
    _debugAssistantRepository(
      'turn decoded conversationId=${turn.conversationId} turnId=${turn.turnId} traceId=${turn.traceId}',
    );
    return turn;
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(AssistantApiMetadata.getAssistantRunPath(runId: runId)),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantRunOperation,
        clientPageId: AssistantRequestPageIds.getAssistantRun,
      ),
    );
    return AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantRunOperation,
      ),
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
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
    var lastSeq = 0;
    var lastEventId = '';
    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      var terminalEventObserved = false;
      try {
        await for (final frame in _openAssistantRunEventStream(
          runId: runId,
          lastEventId: lastEventId,
        )) {
          final event = frame.event;
          if (event.seq <= lastSeq) {
            continue;
          }
          lastSeq = event.seq;
          if (frame.lastEventId.isNotEmpty) {
            lastEventId = frame.lastEventId;
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
