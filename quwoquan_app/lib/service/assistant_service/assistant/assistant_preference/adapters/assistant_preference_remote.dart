import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantPreferenceInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface,
    });

/// AssistantPreference generated-client command/query adapter。
final class AssistantPreferenceGeneratedAdapter
    implements AssistantPreferenceFacet {
  const AssistantPreferenceGeneratedAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantPreferenceInvocationContextFactory invocationContext;

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
    return client.assistantAssistantPreferenceSetAssistantPreference(
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
      context: invocationContext(
        AssistantRequestPageIds.setAssistantPreference,
        networkSurface: false,
      ),
    );
  }

  @override
  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    final view = await client
        .assistantAssistantPreferenceListAssistantPreferences(
          ListAssistantPreferencesQuery(
            scope: scope?.wireName,
            sessionId: sessionId.trim().isEmpty ? null : sessionId.trim(),
            status: status.wireName,
          ),
          context: invocationContext(
            AssistantRequestPageIds.listAssistantPreferences,
            networkSurface: false,
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
    return client.assistantAssistantPreferenceRevokeAssistantPreference(
      AssistantPreferenceByIdRequest(preferenceId: preferenceId.trim()),
      context: invocationContext(
        AssistantRequestPageIds.revokeAssistantPreference,
        networkSurface: false,
      ),
    );
  }

  @override
  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  }) {
    return client.assistantAssistantPreferenceRestoreAssistantPreference(
      AssistantPreferenceByIdRequest(preferenceId: preferenceId.trim()),
      context: invocationContext(
        AssistantRequestPageIds.restoreAssistantPreference,
        networkSurface: false,
      ),
    );
  }
}
