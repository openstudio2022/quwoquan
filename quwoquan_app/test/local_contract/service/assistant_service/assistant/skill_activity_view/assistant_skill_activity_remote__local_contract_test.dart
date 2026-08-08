// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
// readiness_case: skill_activity_view_list_skill_activities_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_activity_view/adapters/skill_activity_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test('SkillActivity uses one typed owner-scoped generated query', () async {
    late http.Request captured;
    final httpClient = CloudHttpClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode(<String, Object?>{
            'items': <Object?>[
              <String, Object?>{
                'activityId': 'activity-1',
                'skillId': 'travel_companion',
                'activityKind': 'data_control',
                'status': 'failed',
                'displayKey': 'assistant.skill_activity.data_control.failed',
                'sourceObjectRef':
                    'assistant.SkillDataControlRequest:control-1',
                'sourceRevision': 2,
                'dataControlRequestId': 'control-1',
                'failureCode':
                    'ASSISTANT.SYSTEM.skill_data_control_unavailable',
                'recoveryAction': 'retry_data_control',
                'occurredAt': '2026-08-04T00:00:00Z',
              },
            ],
            'nextCursor': null,
            'externalSources': <Object?>[],
          }),
          200,
          request: request,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _ActivityAuthTokenProvider(),
    );
    final adapter = RemoteAssistantSkillActivityAdapter(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.assistantSkills.id,
        routeId: AppUiSurfaces.assistantSkills.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(
          accountId: 'assistant-test-account',
          personaId: 'assistant-test-persona',
        ),
      ),
    );

    final result = await adapter.listSkillActivities(
      skillId: 'travel_companion',
      cursor: 'cursor-1',
      limit: 20,
    );

    expect(captured.method, 'GET');
    expect(captured.url.path, '/assistant/skills/travel_companion/activities');
    expect(captured.url.queryParameters, <String, String>{
      'cursor': 'cursor-1',
      'limit': '20',
    });
    expect(result.items.single.activityKind, SkillActivityKind.dataControl);
    expect(
      result.items.single.displayKey,
      SkillActivityDisplayKey.dataControlFailed,
    );
    expect(
      result.items.single.recoveryAction,
      SkillActivityRecoveryAction.retryDataControl,
    );
    expect(result.items.single.dataControlRequestId, 'control-1');
  });
}

final class _ActivityAuthTokenProvider implements CloudAuthTokenProvider {
  const _ActivityAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-activity-test-token';
}
