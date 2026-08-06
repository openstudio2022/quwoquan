import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantPreference 的对象级 command/query facade。
abstract class AssistantPreferenceFacet {
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  });

  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  });

  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  });

  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  });
}
