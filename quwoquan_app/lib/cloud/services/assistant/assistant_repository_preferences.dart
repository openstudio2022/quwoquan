part of 'assistant_repository.dart';

/// Assistant preference fact command and query transport.
mixin _RemoteAssistantPreference on _RemoteAssistantRepositoryBase
    implements AssistantPreferenceFacet {
  @override
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  }) {
    return _core.setPreference(
      SetAssistantPreferenceRequest(
        scope: scope,
        sessionId: sessionId.trim().isEmpty ? null : sessionId.trim(),
        kind: kind,
        value: value.trim(),
        sourceType: sourceType,
        sourceSessionId: sourceSessionId.trim().isEmpty
            ? null
            : sourceSessionId.trim(),
        confirmed: confirmed,
      ),
    );
  }

  @override
  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    final view = await _core.listPreferences(
      ListAssistantPreferencesQuery(
        scope: scope?.wireName,
        sessionId: sessionId.trim().isEmpty ? null : sessionId.trim(),
        status: status.wireName,
      ),
    );
    return view.items
        .where((preference) => preference.preferenceId.trim().isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  }) {
    return _core.revokePreference(preferenceId.trim());
  }

  @override
  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  }) {
    return _core.restorePreference(preferenceId.trim());
  }
}
