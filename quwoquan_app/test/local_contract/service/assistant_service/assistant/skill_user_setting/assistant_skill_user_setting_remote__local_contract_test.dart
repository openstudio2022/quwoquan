// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// readiness_case: skill_user_setting_list_skill_user_settings_app_local
// readiness_case: skill_user_setting_get_skill_user_setting_app_local
// readiness_case: skill_user_setting_put_skill_user_setting_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/adapters/skill_user_setting_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';
import '../../../../../support/runtime/codec/canonical_digest_fixture.dart';

const _configurationSchema = <String, Object?>{
  'type': 'object',
  'additionalProperties': false,
  'properties': <String, Object?>{
    'pace': <String, Object?>{
      'type': 'string',
      'enum': <String>['relaxed', 'balanced'],
    },
  },
};

final _configurationSchemaDigest = canonicalFixtureSha256(_configurationSchema);

void main() {
  test('SkillUserSetting generated adapter owns list/get/put wire', () async {
    final requests = <http.Request>[];
    final httpClient = CloudHttpClient(
      client: MockClient((request) async {
        requests.add(request);
        final response =
            request.method == 'GET' &&
                request.url.path == '/assistant/skill-settings'
            ? <String, Object?>{
                'items': <Object?>[_settingResponse()],
              }
            : request.method == 'PUT'
            ? <String, Object?>{
                'setting': _settingResponse(status: 'disabled', revision: 2),
                'changed': true,
                'replayed': false,
              }
            : _settingResponse();
        return http.Response(
          jsonEncode(response),
          200,
          request: request,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _SettingAuthTokenProvider(),
    );
    final adapter = RemoteAssistantSkillUserSettingAdapter(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: _invocationContext,
    );

    final listed = await adapter.listSkillUserSettings();
    final fetched = await adapter.getSkillUserSetting(
      skillId: 'travel_companion',
    );
    final updated = await adapter.putSkillUserSetting(
      skillId: 'travel_companion',
      status: SkillUserSettingStatus.disabled,
      configurationData: const <String, Object?>{'pace': 'relaxed'},
      configurationSchemaDigest: _configurationSchemaDigest,
      memoryPolicy: SkillMemoryPolicy.confirmBeforeSave,
      connectorConnectionRefs: const <String>['calendar:primary'],
      expectedRevision: 1,
      clientRequestId: 'setting-intent-1',
    );

    expect(listed.single.skillId, 'travel_companion');
    expect(fetched.status, SkillUserSettingStatus.enabled);
    expect(updated.setting.status, SkillUserSettingStatus.disabled);
    expect(requests.map((request) => request.url.path), <String>[
      '/assistant/skill-settings',
      '/assistant/skills/travel_companion/setting',
      '/assistant/skills/travel_companion/setting',
    ]);
    expect(requests.last.headers['Idempotency-Key'], 'setting-intent-1');
    expect(jsonDecode(requests.last.body), <String, Object?>{
      'status': 'disabled',
      'configurationData': <String, Object?>{'pace': 'relaxed'},
      'configurationSchemaDigest': _configurationSchemaDigest,
      'memoryPolicy': 'confirm_before_save',
      'connectorConnectionRefs': <String>['calendar:primary'],
      'expectedRevision': 1,
    });
  });
}

Map<String, Object?> _settingResponse({
  String status = 'enabled',
  int revision = 1,
}) {
  return <String, Object?>{
    'id': 'setting:travel_companion',
    'accountId': 'assistant-test-account',
    'skillId': 'travel_companion',
    'status': status,
    'configurationData': <String, Object?>{'pace': 'relaxed'},
    'configurationSchemaDigest': _configurationSchemaDigest,
    'memoryPolicy': 'confirm_before_save',
    'connectorConnectionRefs': <String>['calendar:primary'],
    'revision': revision,
    'createdAt': '2026-08-02T00:00:00Z',
    'updatedAt': '2026-08-02T00:00:00Z',
  };
}

CloudOperationInvocationContext _invocationContext(
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.assistantSkills.id,
    routeId: AppUiSurfaces.assistantSkills.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'assistant-test-account',
      personaId: 'assistant-test-persona',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _SettingAuthTokenProvider implements CloudAuthTokenProvider {
  const _SettingAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-setting-test-token';
}
