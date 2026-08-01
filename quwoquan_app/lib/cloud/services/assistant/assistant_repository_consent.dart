part of 'assistant_repository.dart';

/// Skill consent read and state-transition transport.
mixin _RemoteAssistantSkillConsent on _RemoteAssistantRepositoryBase
    implements AssistantSkillConsentFacet {
  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    final uri = _assistantUri(AssistantApiMetadata.listConsentsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSettings(
        operationId: AssistantApiMetadata.listConsentsOperation,
        clientPageId: AssistantRequestPageIds.listConsents,
      ),
    );
    final object = decoded is List
        ? <String, dynamic>{'items': decoded}
        : CloudResponseDecoder.asObject(
            decoded,
            context: _settingsContext(
              operationId: AssistantApiMetadata.listConsentsOperation,
            ),
          );
    final rawItems =
        (object['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final consents = rawItems
        .map(AssistantSkillConsent.fromJson)
        .where((item) => item.skillId.isNotEmpty)
        .toList(growable: false);
    await _store.save(consents);
    return consents;
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
    required String clientRequestId,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AssistantApiMetadata.grantSkillConsentOperation,
    );
    final path = AssistantApiMetadata.grantSkillConsentPath(skillId: skillId);
    final uri = _assistantUri(path);
    final decoded = await _httpClient.postJson(
      uri,
      headers: <String, String>{
        ..._headersForSettings(
          operationId: AssistantApiMetadata.grantSkillConsentOperation,
          clientPageId: AssistantRequestPageIds.grantSkillConsent,
        ),
        'Idempotency-Key': requestId,
      },
      body: <String, dynamic>{'grantedScope': grantedScope},
    );
    try {
      final object = CloudResponseDecoder.asObject(
        decoded,
        context: _settingsContext(
          operationId: AssistantApiMetadata.grantSkillConsentOperation,
        ),
      );
      final payload =
          (object['consent'] as Map?)?.cast<String, dynamic>() ?? object;
      final consent = AssistantSkillConsent.fromJson(payload);
      if (consent.skillId != skillId || !consent.granted) {
        throw const FormatException(
          'assistant consent grant response is not authoritative',
        );
      }
      await _store.upsert(consent);
      return consent;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AssistantApiMetadata.revokeSkillConsentOperation,
    );
    final uri = _assistantUri(
      AssistantApiMetadata.revokeSkillConsentPath(skillId: skillId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: <String, String>{
        ..._headersForSettings(
          operationId: AssistantApiMetadata.revokeSkillConsentOperation,
          clientPageId: AssistantRequestPageIds.revokeSkillConsent,
        ),
        'Idempotency-Key': requestId,
      },
    );
    await _store.revoke(skillId);
  }
}
