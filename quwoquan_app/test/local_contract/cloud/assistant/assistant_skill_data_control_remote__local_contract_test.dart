// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_data_control_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  test(
    'SkillDataControl keeps one request across create confirm and get',
    () async {
      final requests = <http.Request>[];
      var revision = 1;
      var status = 'pending_confirmation';
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          requests.add(request);
          if (request.method == 'POST' &&
              request.url.path.endsWith('/confirm')) {
            revision = 2;
            status = 'executing';
          }
          final response = request.method == 'GET'
              ? _requestResponse(status: status, revision: revision)
              : <String, Object?>{
                  'request': _requestResponse(
                    status: status,
                    revision: revision,
                  ),
                  'replayed': false,
                };
          return http.Response(
            jsonEncode(response),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _DataControlAuthTokenProvider(),
      );
      final adapter = RemoteAssistantSkillDataControlAdapter(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: _invocationContext,
      );

      final created = await adapter.createSkillDataControlRequest(
        skillId: 'travel_companion',
        requestedActions: const <SkillDataControlAction>[
          SkillDataControlAction.hideActivityHistory,
          SkillDataControlAction.revokeConsent,
        ],
        clientRequestId: 'control-create-intent-1',
      );
      final confirmed = await adapter.confirmSkillDataControlRequest(
        requestId: created.request.requestId,
        expectedRevision: created.request.revision,
        confirmed: true,
        clientRequestId: 'control-confirm-intent-1',
      );
      final fetched = await adapter.getSkillDataControlRequest(
        requestId: confirmed.request.requestId,
      );

      expect(created.request.requestId, 'control-1');
      expect(confirmed.request.requestId, created.request.requestId);
      expect(fetched.requestId, created.request.requestId);
      expect(fetched.status, SkillDataControlRequestStatus.executing);
      expect(requests.map((request) => request.url.path), <String>[
        '/assistant/skills/travel_companion/data-control-requests',
        '/assistant/skill-data-control-requests/control-1/confirm',
        '/assistant/skill-data-control-requests/control-1',
      ]);
      expect(requests[0].headers['Idempotency-Key'], 'control-create-intent-1');
      expect(
        requests[1].headers['Idempotency-Key'],
        'control-confirm-intent-1',
      );
      expect(jsonDecode(requests[0].body), <String, Object?>{
        'requestedActions': <String>['hide_activity_history', 'revoke_consent'],
      });
      expect(jsonDecode(requests[1].body), <String, Object?>{
        'expectedRevision': 1,
        'confirmed': true,
      });
    },
  );
}

Map<String, Object?> _requestResponse({
  required String status,
  required int revision,
}) {
  return <String, Object?>{
    'requestId': 'control-1',
    'skillId': 'travel_companion',
    'requestedActions': <String>['hide_activity_history', 'revoke_consent'],
    'completedActions': <String>[],
    'status': status,
    'failedAction': null,
    'failureCode': null,
    'confirmedAt': status == 'pending_confirmation'
        ? null
        : '2026-08-04T00:01:00Z',
    'completedAt': null,
    'createdAt': '2026-08-04T00:00:00Z',
    'updatedAt': '2026-08-04T00:01:00Z',
    'revision': revision,
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

final class _DataControlAuthTokenProvider implements CloudAuthTokenProvider {
  const _DataControlAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-control-test-token';
}
