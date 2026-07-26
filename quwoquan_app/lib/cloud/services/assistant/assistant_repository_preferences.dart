part of 'assistant_repository.dart';

/// Assistant preference fact command and query transport.
mixin _RemoteAssistantPreferenceFact on _RemoteAssistantRepositoryBase
    implements AssistantPreferenceFactFacet {
  @override
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  }) {
    const path = AssistantApiMetadata.setAssistantPreferencePath;
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.setAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.setAssistantPreference,
      body: <String, dynamic>{
        'scope': scope.wireName,
        if (conversationId.trim().isNotEmpty)
          'conversationId': conversationId.trim(),
        'kind': kind.wireName,
        'value': value.trim(),
        'sourceType': sourceType.wireName,
      },
    );
  }

  @override
  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    const path = AssistantApiMetadata.listAssistantPreferencesPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        if (scope != null) 'scope': scope.wireName,
        if (conversationId.trim().isNotEmpty)
          'conversationId': conversationId.trim(),
        'status': status.wireName,
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantPreferencesOperation,
          clientPageId: AssistantRequestPageIds.listAssistantPreferences,
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
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.listAssistantPreferencesOperation,
              ),
            );
      return AssistantPreferenceFactListView.fromJson(decoded).items
          .where((fact) => fact.preferenceId.trim().isNotEmpty)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  }) {
    final path = AssistantApiMetadata.revokeAssistantPreferencePath(
      preferenceId: preferenceId.trim(),
    );
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.revokeAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.revokeAssistantPreference,
    );
  }

  @override
  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  }) {
    final path = AssistantApiMetadata.restoreAssistantPreferencePath(
      preferenceId: preferenceId.trim(),
    );
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.restoreAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.restoreAssistantPreference,
    );
  }

  Future<AssistantPreferenceFact> _postAssistantPreference({
    required String path,
    required String operationId,
    required String clientPageId,
    Map<String, dynamic>? body,
  }) async {
    try {
      final response = await _httpClient.post(
        _assistantUri(path),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId: operationId,
            clientPageId: clientPageId,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(body ?? const <String, dynamic>{}),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = CloudResponseDecoder.asObject(
        jsonDecode(response.body),
        context: _personalAssistantDialogContext(operationId: operationId),
      );
      final fact = AssistantPreferenceFact.fromJson(decoded);
      if (fact.preferenceId.trim().isEmpty) {
        throw const FormatException(
          'assistant preference response is missing preferenceId',
        );
      }
      return fact;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }
}
