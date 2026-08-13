// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/adapters/skill_surface_placement_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test('SkillSurfacePlacement generated adapter owns get/put wire', () async {
    final requests = <http.Request>[];
    final httpClient = CloudHttpClient(
      client: MockClient((request) async {
        requests.add(request);
        final response = request.method == 'PUT'
            ? _placementResponse(
                disabledSkillIds: const <String>[
                  'news_briefing',
                  'travel_companion',
                ],
                revision: 4,
              )
            : _placementResponse(
                disabledSkillIds: const <String>['news_briefing'],
                revision: 3,
              );
        return http.Response(
          jsonEncode(response),
          200,
          request: request,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _PlacementAuthTokenProvider(),
    );
    final adapter = RemoteAssistantSkillSurfacePlacementAdapter(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: _invocationContext,
    );

    final fetched = await adapter.getSkillSurfacePlacement(
      surfaceKind: SkillSurfaceKind.conversation,
      surfaceId: 'conv-42',
    );
    final saved = await adapter.putSkillSurfacePlacement(
      surfaceKind: SkillSurfaceKind.conversation,
      surfaceId: 'conv-42',
      policy: SkillSurfacePlacementPolicy.allSharedEligible,
      disabledSkillIds: const <String>['news_briefing', 'travel_companion'],
      status: SkillSurfacePlacementStatus.active,
      expectedRevision: 3,
      clientRequestId: 'placement-intent-1',
    );

    expect(fetched.surfaceKind, SkillSurfaceKind.conversation);
    expect(fetched.surfaceId, 'conv-42');
    expect(fetched.policy, SkillSurfacePlacementPolicy.allSharedEligible);
    expect(fetched.disabledSkillIds, <String>['news_briefing']);
    expect(fetched.status, SkillSurfacePlacementStatus.active);
    expect(fetched.revision, 3);
    expect(saved.disabledSkillIds, <String>[
      'news_briefing',
      'travel_companion',
    ]);
    expect(saved.revision, 4);

    expect(requests.map((request) => request.method), <String>['GET', 'PUT']);
    expect(requests.map((request) => request.url.path), <String>[
      '/assistant/skill-placements/conversation/conv-42',
      '/assistant/skill-placements/conversation/conv-42',
    ]);
    expect(requests.last.headers['Idempotency-Key'], 'placement-intent-1');
    expect(jsonDecode(requests.last.body), <String, Object?>{
      'policy': 'all_shared_eligible',
      'disabledSkillIds': <String>['news_briefing', 'travel_companion'],
      'status': 'active',
      'expectedRevision': 3,
    });
  });
}

Map<String, Object?> _placementResponse({
  List<String> disabledSkillIds = const <String>[],
  int revision = 1,
}) {
  return <String, Object?>{
    'id': 'placement:conversation:conv-42',
    'surfaceKind': 'conversation',
    'surfaceId': 'conv-42',
    'policy': 'all_shared_eligible',
    'disabledSkillIds': disabledSkillIds,
    'status': 'active',
    'revision': revision,
    'createdAt': '2026-08-01T00:00:00Z',
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

final class _PlacementAuthTokenProvider implements CloudAuthTokenProvider {
  const _PlacementAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-placement-test-token';
}
