// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
// readiness_case: assistant_preference_set_assistant_preference_app_api
// readiness_case: assistant_preference_list_assistant_preferences_app_api
// readiness_case: assistant_preference_revoke_assistant_preference_app_api
// readiness_case: assistant_preference_restore_assistant_preference_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

void main() {
  AssistantApiContractHarness? ownerHarness;
  AssistantApiContractHarness? outsiderHarness;

  setUpAll(() async {
    ownerHarness = await AssistantApiContractHarness.create('preference-owner');
    try {
      outsiderHarness = await AssistantApiContractHarness.create(
        'preference-outsider',
      );
    } catch (_) {
      await ownerHarness?.close();
      rethrow;
    }
  });
  tearDownAll(() async {
    try {
      await outsiderHarness?.close();
    } finally {
      await ownerHarness?.close();
    }
  });

  test('production Remote 隔离账号并完成偏好设置、遗忘与撤销恢复', () async {
    final owner = ownerHarness!;
    final outsider = outsiderHarness!;
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    AssistantPreference? preference;

    try {
      preference = await owner.preferences.setAssistantPreference(
        scope: AssistantPreferenceScope.longTerm,
        kind: AssistantPreferenceKind.replyLength,
        value: 'concise-$nonce',
        sourceType: AssistantPreferenceSourceType.management,
      );
      expect(preference.preferenceId, isNotEmpty);
      expect(preference.scope, AssistantPreferenceScope.longTerm);
      expect(preference.status, AssistantPreferenceStatus.active);

      final ownerActive = await owner.preferences.listAssistantPreferences(
        scope: AssistantPreferenceScope.longTerm,
      );
      expect(
        ownerActive.map((item) => item.preferenceId),
        contains(preference.preferenceId),
      );

      final outsiderActive = await outsider.preferences
          .listAssistantPreferences(scope: AssistantPreferenceScope.longTerm);
      expect(
        outsiderActive.map((item) => item.preferenceId),
        isNot(contains(preference.preferenceId)),
      );
      await _expectPreferenceNotFound(
        outsider.preferences.revokeAssistantPreference(
          preferenceId: preference.preferenceId,
        ),
        AppCloudOperationIds
            .assistantAssistantPreferenceRevokeAssistantPreference,
      );

      final revoked = await owner.preferences.revokeAssistantPreference(
        preferenceId: preference.preferenceId,
      );
      expect(revoked.status, AssistantPreferenceStatus.revoked);
      expect(revoked.revokedAt, isNotNull);
      expect(revoked.revocationDeadline, isNotNull);

      final activeAfterRevoke = await owner.preferences
          .listAssistantPreferences(scope: AssistantPreferenceScope.longTerm);
      expect(
        activeAfterRevoke.map((item) => item.preferenceId),
        isNot(contains(preference.preferenceId)),
      );
      final revokedAfterRevoke = await owner.preferences
          .listAssistantPreferences(
            scope: AssistantPreferenceScope.longTerm,
            status: AssistantPreferenceStatus.revoked,
          );
      expect(
        revokedAfterRevoke.map((item) => item.preferenceId),
        contains(preference.preferenceId),
      );

      await _expectPreferenceNotFound(
        outsider.preferences.restoreAssistantPreference(
          preferenceId: preference.preferenceId,
        ),
        AppCloudOperationIds
            .assistantAssistantPreferenceRestoreAssistantPreference,
      );
      final restored = await owner.preferences.restoreAssistantPreference(
        preferenceId: preference.preferenceId,
      );
      expect(restored.status, AssistantPreferenceStatus.active);

      final activeAfterRestore = await owner.preferences
          .listAssistantPreferences(scope: AssistantPreferenceScope.longTerm);
      expect(
        activeAfterRestore.map((item) => item.preferenceId),
        contains(preference.preferenceId),
      );

      final events = await owner.telemetry.waitForEvents(minimumCount: 8);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        containsAll(<String>[
          AppCloudOperationIds
              .assistantAssistantPreferenceSetAssistantPreference,
          AppCloudOperationIds
              .assistantAssistantPreferenceListAssistantPreferences,
          AppCloudOperationIds
              .assistantAssistantPreferenceRevokeAssistantPreference,
          AppCloudOperationIds
              .assistantAssistantPreferenceRestoreAssistantPreference,
        ]),
      );
    } finally {
      if (preference != null) {
        await owner.preferences.revokeAssistantPreference(
          preferenceId: preference.preferenceId,
        );
      }
    }
  });
}

Future<void> _expectPreferenceNotFound(
  Future<AssistantPreference> operation,
  String operationId,
) async {
  await expectLater(
    operation,
    throwsA(
      isA<CloudException>()
          .having((error) => error.statusCode, 'statusCode', 404)
          .having(
            (error) => error.code,
            'code',
            'ASSISTANT.USER.preference_not_found',
          )
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          ),
    ),
  );
}
