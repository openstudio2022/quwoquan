part of 'assistant_repository.dart';

/// Skill subscription command and query transport.
mixin _RemoteAssistantSkillSubscription on _RemoteAssistantRepositoryBase
    implements AssistantSkillSubscriptionFacet {
  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    const path = AssistantApiMetadata.listSkillSubscriptionsPath;
    try {
      final uri = _assistantGetUri(path, {
        'limit': '$limit',
        if (status.trim().isNotEmpty) 'status': status.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
          clientPageId: AssistantRequestPageIds.listSkillSubscriptions,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
        ),
      );
      return rows
          .map(SkillSubscriptionWire.fromJson)
          .where((row) => row.subscriptionId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  }) async {
    final response = await _httpClient.post(
      _assistantUri(AssistantApiMetadata.createSkillSubscriptionPath),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
          clientPageId: AssistantRequestPageIds.createSkillSubscription,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'skillId': skillId,
        'domainId': domainId,
        'tagRefs': tagRefs,
        'searchQueryPlan': <String, dynamic>{
          'rawText': rawText,
          'queries': queries.isEmpty ? <String>[rawText] : queries,
        },
        'trigger': <String, dynamic>{'type': 'cron', 'cron': cron},
        'destination': const <String, dynamic>{'destinationType': 'user'},
      }),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
      ),
    );
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  }) async {
    final response = await _httpClient.patch(
      _assistantUri(
        AssistantApiMetadata.updateSkillSubscriptionStatusPath(
          subscriptionId: subscriptionId,
        ),
      ),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
          clientPageId: AssistantRequestPageIds.updateSkillSubscriptionStatus,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'status': status}),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId:
            AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
      ),
    );
  }
}
