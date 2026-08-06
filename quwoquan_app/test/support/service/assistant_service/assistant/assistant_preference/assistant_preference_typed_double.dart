import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantPreferenceFacet implements AssistantPreferenceFacet {
  final List<AssistantPreference> _preferences = <AssistantPreference>[];

  @override
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final index = _preferences.indexWhere(
      (preference) =>
          preference.scope == scope &&
          (preference.sessionId ?? '') == sessionId.trim() &&
          preference.kind == kind,
    );
    final existing = index < 0 ? null : _preferences[index];
    final preference = AssistantPreference(
      preferenceId:
          existing?.preferenceId ?? 'apf_fixture_${_preferences.length + 1}',
      userId: 'fixture_persona',
      scope: scope,
      sessionId: sessionId.trim().isEmpty ? null : sessionId.trim(),
      kind: kind,
      value: value.trim(),
      sourceType: sourceType,
      sourceSessionId: sourceSessionId.trim().isEmpty
          ? null
          : sourceSessionId.trim(),
      confirmedAt: confirmed ? now : null,
      status: AssistantPreferenceStatus.active,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      version: (existing?.version ?? 0) + 1,
    );
    if (index < 0) {
      _preferences.add(preference);
    } else {
      _preferences[index] = preference;
    }
    return preference;
  }

  @override
  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    return _preferences
        .where(
          (preference) =>
              preference.status == status &&
              (scope == null || preference.scope == scope) &&
              (sessionId.trim().isEmpty ||
                  (preference.sessionId ?? '') == sessionId.trim()),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId.trim(),
    );
    if (index < 0) throw StateError('assistant preference not found');
    final current = _preferences[index];
    if (current.status == AssistantPreferenceStatus.revoked) return current;
    final now = DateTime.now().toUtc();
    final revoked = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.revoked,
      revokedAt: now.toIso8601String(),
      revocationDeadline: now
          .add(const Duration(minutes: 10))
          .toIso8601String(),
      createdAt: current.createdAt,
      updatedAt: now.toIso8601String(),
      version: current.version + 1,
    );
    _preferences[index] = revoked;
    return revoked;
  }

  @override
  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId.trim(),
    );
    if (index < 0) throw StateError('assistant preference not found');
    final current = _preferences[index];
    if (current.status == AssistantPreferenceStatus.active) return current;
    final deadline = DateTime.tryParse(current.revocationDeadline ?? '');
    final now = DateTime.now().toUtc();
    if (deadline == null || !now.isBefore(deadline)) {
      throw StateError('assistant preference restore expired');
    }
    final restored = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.active,
      createdAt: current.createdAt,
      updatedAt: now.toIso8601String(),
      version: current.version + 1,
    );
    _preferences[index] = restored;
    return restored;
  }
}
