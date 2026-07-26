part of 'assistant_repository.dart';

/// Append-only learning telemetry transport.
mixin _RemoteAssistantLearningAppend on _RemoteAssistantRepositoryBase
    implements AssistantLearningAppendFacet {
  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    // 批量部分成功语义：单条失败记录后计入 rejected；全部尝试条目失败时
    // 抛出最后一次结构化异常，部分成功返回 acceptedCount<count 的 ack 由
    // 调用方重试。
    const path = AssistantApiMetadata.reportInteractionEventPath;
    final accepted = <InteractionEvent>[];
    var attempted = 0;
    CloudException? lastFailure;
    for (final event in events) {
      final eventId = event.eventId.trim();
      final runId = event.runId.trim();
      if (eventId.isEmpty || runId.isEmpty) {
        continue;
      }
      attempted += 1;
      try {
        final uri = _assistantUri(path);
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
              operationId: AssistantApiMetadata.reportInteractionEventOperation,
              clientPageId: AssistantRequestPageIds.reportInteractionEvent,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(event.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(event);
        } else {
          lastFailure = CloudErrorMapper.fromStatusCode(
            response.statusCode,
            body: response.body,
            requestPath: path,
          );
          developer.log(
            'interaction event rejected eventId=$eventId status=${response.statusCode}',
            name: 'AssistantLearningAppend',
            error: lastFailure,
          );
        }
      } catch (error) {
        lastFailure = CloudErrorMapper.fromException(error, requestPath: path);
        developer.log(
          'interaction event report failed eventId=$eventId',
          name: 'AssistantLearningAppend',
          error: error,
        );
      }
    }
    final failure = lastFailure;
    if (attempted > 0 && accepted.isEmpty && failure != null) {
      throw failure;
    }
    return AssistantInteractionReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == events.length,
      'acceptedCount': accepted.length,
      'count': events.length,
      'resource': 'interaction_event_batch',
    });
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    // 与 reportInteractionEvents 同一批量部分成功语义。
    const path = AssistantApiMetadata.reportScorecardPath;
    final accepted = <Scorecard>[];
    var attempted = 0;
    CloudException? lastFailure;
    for (final scorecard in scorecards) {
      final scoreId = scorecard.scoreId.trim();
      final eventId = scorecard.eventId.trim();
      if (scoreId.isEmpty || eventId.isEmpty) {
        continue;
      }
      attempted += 1;
      try {
        final uri = _assistantUri(path);
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
              operationId: AssistantApiMetadata.reportScorecardOperation,
              clientPageId: AssistantRequestPageIds.reportScorecard,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(scorecard.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(scorecard);
        } else {
          lastFailure = CloudErrorMapper.fromStatusCode(
            response.statusCode,
            body: response.body,
            requestPath: path,
          );
          developer.log(
            'scorecard rejected eventId=$eventId status=${response.statusCode}',
            name: 'AssistantLearningAppend',
            error: lastFailure,
          );
        }
      } catch (error) {
        lastFailure = CloudErrorMapper.fromException(error, requestPath: path);
        developer.log(
          'scorecard report failed eventId=$eventId',
          name: 'AssistantLearningAppend',
          error: error,
        );
      }
    }
    final failure = lastFailure;
    if (attempted > 0 && accepted.isEmpty && failure != null) {
      throw failure;
    }
    return AssistantScorecardReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == scorecards.length,
      'acceptedCount': accepted.length,
      'count': scorecards.length,
      'resource': 'scorecard_batch',
    });
  }
}
